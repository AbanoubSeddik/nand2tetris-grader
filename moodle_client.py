"""
Moodle REST API client for Constructor University.
Uses participant data for group filtering (group API is restricted).
"""

import aiohttp
import logging
from dataclasses import dataclass, field
from config import MOODLE_URL, MOODLE_TOKEN

log = logging.getLogger(__name__)
API = f"{MOODLE_URL}/webservice/rest/server.php"


@dataclass
class MoodleFile:
    filename: str
    fileurl: str
    filesize: int = 0


@dataclass
class MoodleSubmission:
    user_id: int
    full_name: str
    email: str
    status: str
    grading_status: str
    time_modified: int
    files: list[MoodleFile] = field(default_factory=list)


@dataclass
class MoodleAssignment:
    assign_id: int
    cmid: int
    name: str
    course_id: int
    course_name: str
    max_grade: float
    due_date: int


@dataclass
class MoodleGroup:
    group_id: int
    name: str
    description: str = ""
    member_count: int = 0


async def _call(session, function, **kwargs):
    params = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": function,
        "moodlewsrestformat": "json",
        **kwargs,
    }
    async with session.get(API, params=params) as resp:
        data = await resp.json(content_type=None)
        if isinstance(data, dict) and "exception" in data:
            msg = data.get("message", data.get("errorcode", "Unknown"))
            raise Exception(f"Moodle API [{function}]: {msg}")
        return data


async def test_connection():
    async with aiohttp.ClientSession() as s:
        return await _call(s, "core_webservice_get_site_info")


async def get_courses():
    async with aiohttp.ClientSession() as s:
        info = await _call(s, "core_webservice_get_site_info")
        return await _call(s, "core_enrol_get_users_courses",
                           userid=info["userid"])


async def get_assignments(course_id):
    async with aiohttp.ClientSession() as s:
        data = await _call(s, "mod_assign_get_assignments",
                           **{"courseids[0]": course_id})
        result = []
        for course in data.get("courses", []):
            for a in course.get("assignments", []):
                result.append(MoodleAssignment(
                    assign_id=a["id"], cmid=a["cmid"], name=a["name"],
                    course_id=course["id"],
                    course_name=course.get("fullname", ""),
                    max_grade=float(a.get("grade", 10)),
                    due_date=a.get("duedate", 0)))
        return result


async def _get_participants(assign_id):
    async with aiohttp.ClientSession() as s:
        return await _call(s, "mod_assign_list_participants",
                           assignid=assign_id, groupid=0, filter="")


async def get_groups_from_assignment(assign_id):
    participants = await _get_participants(assign_id)
    group_map = {}
    for p in participants:
        for g in p.get("groups", []):
            gid = g["id"]
            if gid not in group_map:
                group_map[gid] = {"name": g.get("name", ""),
                                  "desc": g.get("description", ""),
                                  "count": 0}
            group_map[gid]["count"] += 1
    groups = []
    for gid, info in sorted(group_map.items(), key=lambda x: x[1]["name"]):
        groups.append(MoodleGroup(
            group_id=gid, name=info["name"],
            description=info["desc"], member_count=info["count"]))
    return groups


async def get_group_member_ids_from_assignment(assign_id, group_id):
    participants = await _get_participants(assign_id)
    ids = set()
    for p in participants:
        for g in p.get("groups", []):
            if g["id"] == group_id:
                ids.add(p["id"])
                break
    return ids


async def find_group_by_name(assign_id, group_name):
    groups = await get_groups_from_assignment(assign_id)
    name_lower = group_name.lower().strip()
    for g in groups:
        if g.name.lower().strip() == name_lower:
            return g
    for g in groups:
        if name_lower in g.name.lower():
            return g
    return None


async def get_submissions(assign_id, group_member_ids=None):
    async with aiohttp.ClientSession() as s:
        sub_data = await _call(s, "mod_assign_get_submissions",
                               **{"assignmentids[0]": assign_id})
        try:
            participants = await _call(
                s, "mod_assign_list_participants",
                assignid=assign_id, groupid=0, filter="")
            user_map = {p["id"]: p for p in participants}
        except Exception:
            user_map = {}

        submissions = []
        for assign in sub_data.get("assignments", []):
            for sub in assign.get("submissions", []):
                uid = sub["userid"]
                if group_member_ids and uid not in group_member_ids:
                    continue
                user = user_map.get(uid, {})
                files = []
                for plugin in sub.get("plugins", []):
                    if plugin.get("type") == "file":
                        for area in plugin.get("fileareas", []):
                            for f in area.get("files", []):
                                files.append(MoodleFile(
                                    filename=f["filename"],
                                    fileurl=f["fileurl"],
                                    filesize=f.get("filesize", 0)))
                if sub.get("status") == "submitted" and files:
                    submissions.append(MoodleSubmission(
                        user_id=uid,
                        full_name=user.get("fullname", f"User {uid}"),
                        email=user.get("email", ""),
                        status=sub["status"],
                        grading_status=user.get("gradingstatus", "notgraded"),
                        time_modified=sub.get("timemodified", 0),
                        files=files))
        return submissions


async def get_ungraded(assign_id, group_member_ids=None):
    subs = await get_submissions(assign_id, group_member_ids)
    return [s for s in subs if s.grading_status == "notgraded"]


async def download_file(file, dest_path):
    url = f"{file.fileurl}?token={MOODLE_TOKEN}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Download failed: HTTP {resp.status}")
            with open(dest_path, 'wb') as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)


async def submit_grade(assign_id, user_id, grade, feedback_html):
    async with aiohttp.ClientSession() as s:
        params = {
            "wstoken": MOODLE_TOKEN,
            "wsfunction": "mod_assign_save_grade",
            "moodlewsrestformat": "json",
            "assignmentid": assign_id, "userid": user_id,
            "grade": grade, "attemptnumber": -1,
            "addattempt": 0, "workflowstate": "", "applytoall": 1,
            "plugindata[assignfeedbackcomments_editor][text]": feedback_html,
            "plugindata[assignfeedbackcomments_editor][format]": 1,
        }
        async with s.post(API, data=params) as resp:
            text = await resp.text()
            if "exception" in text.lower():
                raise Exception(f"Grade submit failed: {text[:300]}")
            log.info(f"Grade submitted: user={user_id} grade={grade}")