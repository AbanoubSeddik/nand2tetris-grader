// Automatic subset of the official Memory.tst.
// Keeps the deterministic RAM and Screen checks and skips
// the interactive keyboard prompts that block batch grading.

load Memory.hdl,
output-file MemoryAutomatic.out,
compare-to MemoryAutomatic.cmp,
output-list in%D1.6.1 load%B2.1.2 address%B1.15.1 out%D1.6.1;

// Prepare overwrite-detection sentinels.
set in 12345, set load 1, set address %X2000, tick, output; tock, output;
set address %X4000, tick, output; tock, output;

set in -1,
set load 1,
set address 0,
tick,
output;
tock,
output;

set in 9999,
set load 0,
tick,
output;
tock,
output;

set address %X2000,
eval,
output;
set address %X4000,
eval,
output;

set in 12345, set load 1, set address %X0000, tick, output; tock, output;
set address %X4000, tick, output; tock, output;

set in 2222,
set load 1,
set address %X2000,
tick,
output;
tock,
output;

set in 9999,
set load 0,
tick,
output;
tock,
output;

set address 0,
eval,
output;
set address %X4000,
eval,
output;

set load 0,
set address %X0001, eval, output;
set address %X0002, eval, output;
set address %X0004, eval, output;
set address %X0008, eval, output;
set address %X0010, eval, output;
set address %X0020, eval, output;
set address %X0040, eval, output;
set address %X0080, eval, output;
set address %X0100, eval, output;
set address %X0200, eval, output;
set address %X0400, eval, output;
set address %X0800, eval, output;
set address %X1000, eval, output;
set address %X2000, eval, output;

set address %X1234,
set in 1234,
set load 1,
tick,
output;
tock,
output;

set load 0,
set address %X2234,
eval, output;
set address %X6234,
eval, output;

set address %X2345,
set in 2345,
set load 1,
tick,
output;
tock,
output;

set load 0,
set address %X0345,
eval, output;
set address %X4345,
eval, output;

// Clear the screen overwrite sentinel before the screen checks.
set in 0, set load 1, set address %X4000, tick, output; tock, output;

set in 12345, set load 1, set address %X0FCF, tick, output; tock, output;
set address %X2FCF, tick, output; tock, output;

set load 1,
set in -1,
set address %X4FCF,
tick,
tock,
output,

set address %X504F,
tick,
tock,
output;

set address %X0FCF,
eval,
output;
set address %X2FCF,
eval,
output;

set load 0,
set address %X4FCE, eval, output;
set address %X4FCD, eval, output;
set address %X4FCB, eval, output;
set address %X4FC7, eval, output;
set address %X4FDF, eval, output;
set address %X4FEF, eval, output;
set address %X4F8F, eval, output;
set address %X4F4F, eval, output;
set address %X4ECF, eval, output;
set address %X4DCF, eval, output;
set address %X4BCF, eval, output;
set address %X47CF, eval, output;
set address %X5FCF, eval, output;
