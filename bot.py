"""
nand2tetris Auto-Grader Bot — Constructor University CH-234
"""

import os
import re
import asyncio
import tempfile
import logging

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters,
)

from config import (
    TELEGRAM_TOKEN, ALLOWED_USER_IDS, TOTAL_POINTS,
    DEFAULT_GROUP, ACTIVE_PROJECT, PROJECTS,
    get_project, detect_project, validate_config,
)
import moodle_client as moodle
import grading_engine as engine
import ai_report as ai
import database as db

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO)
log = logging.getLogger("bot")

PICK_COURSE, PICK_ASSIGN, PICK_GROUP, REVIEWING, TYPING_GRADE = range(5)


def auth(func):
    async def wrap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if ALLOWED_USER_IDS and uid not in ALLOWED_USER_IDS:
            await update.effective_message.reply_text(
                f"Not authorized. Your Telegram ID: {uid}\n"
                f"Add it to ALLOWED_USER_IDS in .env")
            return ConversationHandler.END
        return await func(update, ctx)
    return wrap


@auth
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    g = f"\nDefault group: {DEFAULT_GROUP}" if DEFAULT_GROUP else ""
    await update.message.reply_text(
        f"nand2tetris Auto-Grader\n"
        f"Constructor University -- CH-234{g}\n\n"
        f"/grade -- Grade an assignment\n"
        f"/test -- Test Moodle connection\n"
        f"/status -- Session status\n"
        f"/cancel -- Stop current flow")


@auth
async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Testing Moodle...")
    try:
        info = await moodle.test_connection()
        await msg.edit_text(
            f"Connected!\n"
            f"Site: {info.get('sitename','?')}\n"
            f"User: {info.get('fullname','?')}\n"
            f"ID: {info.get('userid','?')}")
    except Exception as e:
        await msg.edit_text(f"Failed: {e}")


@auth
async def cmd_grade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Fetching courses...")
    try:
        courses = await moodle.get_courses()
    except Exception as e:
        await msg.edit_text(f"Error: {e}")
        return ConversationHandler.END
    if not courses:
        await msg.edit_text("No courses found.")
        return ConversationHandler.END
    ctx.user_data["courses"] = {c["id"]: c for c in courses}
    buttons = [[InlineKeyboardButton(
        f"{c.get('shortname','')} -- {c['fullname'][:40]}",
        callback_data=f"c_{c['id']}")] for c in courses[:15]]
    await msg.edit_text("Select a course:",
                        reply_markup=InlineKeyboardMarkup(buttons))
    return PICK_COURSE


async def pick_course(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split("_")[1])
    ctx.user_data["course_id"] = cid
    await q.edit_message_text("Fetching assignments...")
    try:
        assigns = await moodle.get_assignments(cid)
    except Exception as e:
        await q.edit_message_text(f"Error: {e}")
        return ConversationHandler.END
    if not assigns:
        await q.edit_message_text("No assignments found.")
        return ConversationHandler.END
    ctx.user_data["assigns"] = {a.assign_id: a for a in assigns}
    buttons = [[InlineKeyboardButton(
        a.name[:50], callback_data=f"a_{a.assign_id}")]
        for a in assigns]
    await q.edit_message_text("Select assignment:",
                              reply_markup=InlineKeyboardMarkup(buttons))
    return PICK_ASSIGN

async def pick_assign(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    aid = int(q.data.split("_")[1])
    assign = ctx.user_data["assigns"][aid]
    ctx.user_data["assign_id"] = aid
    ctx.user_data["assign"] = assign

    # Auto-detect project
    detected = detect_project(assign.name)
    if detected:
        ctx.user_data["project_num"] = detected["number"]
        log.info(f"Auto-detected Project {detected['number']}: "
                 f"{detected['name']}")
    else:
        ctx.user_data["project_num"] = ACTIVE_PROJECT
        log.warning(f"Could not detect project from '{assign.name}', "
                    f"using ACTIVE_PROJECT={ACTIVE_PROJECT}")

    proj = get_project(ctx.user_data["project_num"])
    ctx.user_data["total_pts"] = proj["total_points"]

    # Try default group
    if DEFAULT_GROUP:
        await q.edit_message_text(
            f"Detected: HW{proj['number']} -- {proj['name']}\n"
            f"Looking for group {DEFAULT_GROUP}...")
        try:
            group = await moodle.find_group_by_name(aid, DEFAULT_GROUP)
            if group:
                ctx.user_data["group"] = group
                member_ids = \
                    await moodle.get_group_member_ids_from_assignment(
                        aid, group.group_id)
                ctx.user_data["group_member_ids"] = member_ids
                buttons = [
                    [InlineKeyboardButton(
                        f"Grade {group.name} ({len(member_ids)} students)",
                        callback_data=f"g_{group.group_id}")],
                    [InlineKeyboardButton(
                        "Pick different group",
                        callback_data="g_pick")],
                    [InlineKeyboardButton(
                        "Grade ALL students",
                        callback_data="g_all")],
                ]
                await q.edit_message_text(
                    f"HW{proj['number']}: {proj['name']}\n"
                    f"Components: {len(proj['chip_names'])}, "
                    f"Total: {proj['total_points']} pts\n"
                    f"Group: {group.name} ({len(member_ids)} students)\n"
                    f"Partial credit: enabled",
                    reply_markup=InlineKeyboardMarkup(buttons))
                return PICK_GROUP
            else:
                log.warning(f"Default group '{DEFAULT_GROUP}' not found")
        except Exception as e:
            log.warning(f"Group lookup failed: {e}")

    return await _show_group_picker(q, ctx)


async def _show_group_picker(q, ctx):
    aid = ctx.user_data["assign_id"]
    try:
        groups = await moodle.get_groups_from_assignment(aid)
    except Exception as e:
        await q.edit_message_text(f"Could not fetch groups: {e}\n"
                                  f"Grading all students...")
        ctx.user_data["group_member_ids"] = None
        ctx.user_data["group"] = None
        return await _start_grading(q, ctx)
    if not groups:
        await q.edit_message_text("No groups found. Grading all...")
        ctx.user_data["group_member_ids"] = None
        ctx.user_data["group"] = None
        return await _start_grading(q, ctx)
    ctx.user_data["groups_map"] = {g.group_id: g for g in groups}
    buttons = [[InlineKeyboardButton(
        f"{g.name} ({g.member_count} students)",
        callback_data=f"g_{g.group_id}")] for g in groups]
    buttons.append([InlineKeyboardButton(
        "Grade ALL students", callback_data="g_all")])
    await q.edit_message_text("Select a group to grade:",
                              reply_markup=InlineKeyboardMarkup(buttons))
    return PICK_GROUP


async def pick_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    aid = ctx.user_data["assign_id"]

    if data == "g_pick":
        return await _show_group_picker(q, ctx)

    if data == "g_all":
        ctx.user_data["group_member_ids"] = None
        ctx.user_data["group"] = None
        return await _start_grading(q, ctx)

    group_id = int(data.split("_")[1])
    if not ctx.user_data.get("group_member_ids"):
        try:
            ids = await moodle.get_group_member_ids_from_assignment(
                aid, group_id)
            ctx.user_data["group_member_ids"] = ids
        except Exception as e:
            await q.edit_message_text(f"Error: {e}")
            ctx.user_data["group_member_ids"] = None

    if not ctx.user_data.get("group"):
        gmap = ctx.user_data.get("groups_map", {})
        if group_id in gmap:
            ctx.user_data["group"] = gmap[group_id]

    return await _start_grading(q, ctx)


async def _start_grading(q, ctx):
    aid = ctx.user_data["assign_id"]
    assign = ctx.user_data["assign"]
    group = ctx.user_data.get("group")
    group_member_ids = ctx.user_data.get("group_member_ids")
    proj = get_project(ctx.user_data.get("project_num"))
    total_pts = proj["total_points"]
    ctx.user_data["total_pts"] = total_pts

    group_label = f" ({group.name})" if group else " (all students)"

    await q.edit_message_text(
        f"Fetching ungraded submissions for:\n"
        f"{assign.name}{group_label}")

    try:
        subs = await moodle.get_ungraded(aid, group_member_ids)
    except Exception as e:
        await q.edit_message_text(f"Error: {e}")
        return ConversationHandler.END

    # Resume behavior: avoid re-grading users already submitted in
    # previous local sessions for the same assignment.
    previously_submitted_ids = \
        await db.get_submitted_user_ids_for_assignment(aid)
    skipped_local = 0
    if previously_submitted_ids:
        before = len(subs)
        subs = [s for s in subs if s.user_id not in previously_submitted_ids]
        skipped_local = before - len(subs)
        if skipped_local > 0:
            log.info(
                f"Filtered {skipped_local} already-submitted students "
                f"from local session history (assignment {aid})")

    if not subs:
        if skipped_local > 0:
            await q.edit_message_text(
                f"No pending submissions in{group_label}.\n"
                f"Skipped {skipped_local} already submitted student(s) "
                f"from previous local sessions.")
        else:
            await q.edit_message_text(
                f"All submissions in{group_label} are already graded!")
        return ConversationHandler.END

    resume_note = (
        f"Resumed: skipped {skipped_local} already submitted student(s)\n"
        if skipped_local > 0 else
        "")
    status = await q.message.reply_text(
        f"{len(subs)} ungraded submissions{group_label}\n"
        f"{resume_note}"
        f"HW{proj['number']}: {proj['name']}\n"
        f"Starting batch grading...\n\n"
        f"Grading 0/{len(subs)}...")

    session_id = await db.create_session(
        aid, assign.name, proj["number"])
    ctx.user_data["session_id"] = session_id
    queue = []

    for i, sub in enumerate(subs):
        try:
            await status.edit_text(
                f"Grading {i+1}/{len(subs)}: {sub.full_name}...")
        except Exception:
            pass

        archive_file = next(
            (f for f in sub.files if f.filename.lower().endswith(
                ('.zip', '.rar'))),
            None)

        if not archive_file:
            rid = await db.save_result(
                session_id, sub.user_id, sub.full_name,
                0, [], "No supported archive (.zip/.rar) in submission.")
            queue.append({
                "rid": rid, "name": sub.full_name, "uid": sub.user_id,
                "score": 0,
                "report": "No supported archive (.zip/.rar) found in "
                          "submission.",
                "header": f"❌ {sub.full_name}\n"
                          f"Score: 0/{total_pts} (0%)"})
            continue

        suffix = ".rar" if archive_file.filename.lower().endswith(
            ".rar") else ".zip"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            await moodle.download_file(archive_file, tmp.name)
            tmp.close()

            gr = await engine.grade_student(
                tmp.name, sub.full_name, sub.user_id,
                project_num=ctx.user_data.get("project_num"),
                zip_filename=archive_file.filename)

            report = await ai.generate_report(gr)
            header = ai.format_header(gr)

            chips = [{"name": c.name, "passed": c.passed,
                      "pts": c.points, "max": c.max_points,
                      "err": c.error_type, "msg": c.error_msg}
                     for c in gr.chips]

            rid = await db.save_result(
                session_id, sub.user_id, sub.full_name,
                gr.total_earned, chips, report)

            queue.append({
                "rid": rid, "name": sub.full_name, "uid": sub.user_id,
                "score": gr.total_earned, "report": report,
                "header": header})

        except Exception as e:
            log.error(f"Error grading {sub.full_name}: {e}",
                      exc_info=True)
            rid = await db.save_result(
                session_id, sub.user_id, sub.full_name,
                0, [], f"Error: {str(e)[:200]}")
            queue.append({
                "rid": rid, "name": sub.full_name, "uid": sub.user_id,
                "score": 0,
                "report": f"Grading error: {str(e)[:200]}",
                "header": f"⚠️ {sub.full_name}\nGrading error"})
        finally:
            os.unlink(tmp.name)

    avg = sum(r["score"] for r in queue) / len(queue) if queue else 0
    await status.edit_text(
        f"Batch grading complete!{group_label}\n\n"
        f"{len(queue)} submissions graded\n"
        f"Average: {avg:.1f}/{total_pts}\n\n"
        f"Now showing results for review...")

    ctx.user_data["queue"] = queue
    ctx.user_data["idx"] = 0

    await asyncio.sleep(1)
    await _show_next(q.message.chat_id, ctx)
    return REVIEWING


async def _show_next(chat_id, ctx):
    queue = ctx.user_data.get("queue", [])
    idx = ctx.user_data.get("idx", 0)
    total_pts = ctx.user_data.get("total_pts", TOTAL_POINTS)

    if idx >= len(queue):
        sid = ctx.user_data["session_id"]
        summary = await db.get_session_summary(sid)
        group = ctx.user_data.get("group")
        gl = f"\nGroup: {group.name}" if group else ""
        await ctx.bot.send_message(chat_id,
            f"🎉 Session complete!{gl}\n\n"
            f"Submitted: {summary.get('submitted', 0)}\n"
            f"Skipped: {summary.get('skipped', 0)}\n"
            f"Average: {summary.get('avg_score', 0):.1f}/{total_pts}\n"
            f"Total: {summary.get('total', 0)}")
        return

    item = queue[idx]
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Review {idx+1}/{len(queue)}\n\n"
        f"{item['header']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{item['report']}")

    if len(text) > 4000:
        text = text[:3950] + "\n\n... (truncated)"

    score = item["score"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"✅ Submit {score}/{total_pts}",
            callback_data=f"sub_{item['rid']}_{score}")],
        [InlineKeyboardButton(
            "✏️ Change Grade",
            callback_data=f"edit_{item['rid']}"),
         InlineKeyboardButton(
            "📋 Copy Report",
            callback_data=f"copy_{item['rid']}")],
        [InlineKeyboardButton(
            "⏭ Skip",
            callback_data=f"skip_{item['rid']}")],
    ])
    await ctx.bot.send_message(chat_id, text, reply_markup=kb)


async def review_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    queue = ctx.user_data.get("queue", [])
    idx = ctx.user_data.get("idx", 0)
    total_pts = ctx.user_data.get("total_pts", TOTAL_POINTS)

    if idx >= len(queue):
        return REVIEWING

    item = queue[idx]
    aid = ctx.user_data["assign_id"]

    if data.startswith("sub_"):
        parts = data.split("_")
        rid = int(parts[1])
        grade = float(parts[2])
        try:
            feedback_html = (
                f"<p><strong>Score: {grade}/{total_pts}</strong></p>"
                f"<p>{item['report'].replace(chr(10), '<br>')}</p>")
            await moodle.submit_grade(aid, item["uid"],
                                      grade, feedback_html)
            await db.mark_submitted(rid, grade)
            await q.edit_message_text(
                q.message.text +
                f"\n\n✅ Submitted: {grade}/{total_pts}")
        except Exception as e:
            await q.edit_message_text(
                q.message.text +
                f"\n\n❌ Failed: {str(e)[:100]}")
            return REVIEWING

        ctx.user_data["idx"] = idx + 1
        await asyncio.sleep(0.5)
        await _show_next(update.effective_chat.id, ctx)
        return REVIEWING

    elif data.startswith("skip_"):
        rid = int(data.split("_")[1])
        await db.mark_skipped(rid)
        await q.edit_message_text(
            q.message.text + "\n\n⏭ Skipped")
        ctx.user_data["idx"] = idx + 1
        await asyncio.sleep(0.5)
        await _show_next(update.effective_chat.id, ctx)
        return REVIEWING

    elif data.startswith("edit_"):
        ctx.user_data["edit_rid"] = int(data.split("_")[1])
        await q.message.reply_text(
            f"Type the new grade (0 to {total_pts}):")
        return TYPING_GRADE

    elif data.startswith("copy_"):
        report = item["report"]
        await q.message.reply_text(
            f"Score: {item['score']}/{total_pts}\n\n{report}")
        return REVIEWING

    return REVIEWING


async def type_grade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    total_pts = ctx.user_data.get("total_pts", TOTAL_POINTS)
    try:
        grade = round(float(text), 2)
        assert 0 <= grade <= total_pts
    except (ValueError, AssertionError):
        await update.message.reply_text(
            f"Enter a number between 0 and {total_pts}:")
        return TYPING_GRADE

    idx = ctx.user_data.get("idx", 0)
    queue = ctx.user_data.get("queue", [])
    item = queue[idx]
    old = item["score"]
    item["score"] = grade

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"✅ Submit {grade}/{total_pts}",
            callback_data=f"sub_{item['rid']}_{grade}"),
         InlineKeyboardButton(
            f"↩️ Reset to {old}",
            callback_data=f"sub_{item['rid']}_{old}")],
        [InlineKeyboardButton(
            "⏭ Skip",
            callback_data=f"skip_{item['rid']}")],
    ])
    await update.message.reply_text(
        f"Grade changed to {grade}/{total_pts}",
        reply_markup=kb)
    return REVIEWING


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sid = ctx.user_data.get("session_id")
    if not sid:
        await update.message.reply_text("No active session. Use /grade")
        return
    s = await db.get_session_summary(sid)
    total_pts = ctx.user_data.get("total_pts", TOTAL_POINTS)
    group = ctx.user_data.get("group")
    gl = f"\nGroup: {group.name}" if group else ""
    await update.message.reply_text(
        f"Session Status{gl}\n\n"
        f"Submitted: {s.get('submitted',0)}\n"
        f"Skipped: {s.get('skipped',0)}\n"
        f"Pending: {s.get('pending',0)}\n"
        f"Average: {s.get('avg_score',0):.1f}/{total_pts}")


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Session paused. /grade to start new.")
    return ConversationHandler.END


async def post_init(app):
    await db.init_db()
    await app.bot.set_my_commands([
        BotCommand("grade", "Grade an assignment"),
        BotCommand("test", "Test Moodle connection"),
        BotCommand("status", "Session status"),
        BotCommand("cancel", "Cancel current flow"),
    ])
    log.info("Bot initialized")


def main():
    issues = validate_config()
    for issue in issues:
        lvl = "ERROR" if "TOKEN" in issue.upper() else "WARN"
        print(f"  [{lvl}] {issue}")

    if not TELEGRAM_TOKEN:
        print("\nTELEGRAM_TOKEN is required. Set it in .env")
        return

    print(f"  Default group: {DEFAULT_GROUP or 'None'}")
    print(f"  Active project: {ACTIVE_PROJECT}")

    app = Application.builder().token(TELEGRAM_TOKEN) \
        .post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("grade", cmd_grade)],
        states={
            PICK_COURSE: [
                CallbackQueryHandler(pick_course, pattern=r"^c_")],
            PICK_ASSIGN: [
                CallbackQueryHandler(pick_assign, pattern=r"^a_")],
            PICK_GROUP: [
                CallbackQueryHandler(pick_group, pattern=r"^g_")],
            REVIEWING: [
                CallbackQueryHandler(review_action,
                                     pattern=r"^(sub|skip|edit|copy)_")],
            TYPING_GRADE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               type_grade)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(conv)

    print("\n🤖 Bot starting... Press Ctrl+C to stop.\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
