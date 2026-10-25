#!/usr/bin/env python3
"""Wave-5b regressions: watch/parallel quoted command strings, parallel ::::, Windows root wildcards, any-order Remove-Item flags,
diskpart/format.com/bcdedit/reg/wmic, plus benign neighbours. Timing inputs stay linear."""
import pathlib, sys, time, importlib.util
sp = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
spec = importlib.util.spec_from_file_location("dg", sp); dg = importlib.util.module_from_spec(spec); spec.loader.exec_module(dg)
BAD = [
    'watch "rm -rf /home"', "watch -n1 'rm -rf /etc'", 'cat list | parallel "rm -rf {}"', "parallel 'rm -rf {}'",
    "parallel -j4 rm -rf :::: list", "parallel 'rm -rf {}' ::: /etc /home",
    "del /f /q C:\\*", "cmd /c del C:\\*.*", 'powershell -c "rm -r -fo C:/x"', "del -Recurse C:\\x",
    "Get-ChildItem | Remove-Item -Recurse", "Get-ChildItem | Remove-Item -Force -Recurse", "Remove-Item -Force -Recurse C:\\x",
    "format.com C:", "diskpart", "echo list disk | diskpart", "bcdedit /delete {current}", "reg delete HKLM\\x /f",
    "wmic logicaldisk delete",
    "watch -d 'rm -rf /'", "watch --interval 1 'rm -rf /'", "watch -d rm -rf /", "watch -n1 -d 'rm -rf /'", "watch --differences=cumulative -t 'rm -rf /'",
    "watch -n 2 -d -t -p -x rm -rf /etc", "reg delete /f HKLM\\x", "reg delete \\\\host\\HKLM\\x", "del C:\\Windows\\*", "del C:/Users/*", "format c:\\",
    "format c:\\ /q", "format d:\\ /fs:ntfs", "format e:\\ /y", "del %SystemRoot%\\*", "del %windir%\\system32\\*", "del \\Windows\\*", "del C:\\Windows\\Temp\\*.*",
    "wmic volume where DriveLetter='C:' call format",
]
GOOD = [
    "watch -n1 ls", 'watch "ls -l"', "parallel -j4 echo {} ::: a b", "parallel 'echo {}' ::: a b", "cat list | parallel 'wc -l {}'",
    "del build\\out.txt", "del /q out.log", "Remove-Item foo.txt", "reg query HKLM\\x", "bcdedit /enum", "wmic os get caption",
    "del C:\\Users\\bob\\proj\\*.tmp", "del C:\\Windows\\Temp\\*.tmp", "format.exe /?", "rm -r build", "watch -d ls", "watch --interval 1 ls -l", "watch -n1 -d 'ls -l'", "del C:\\temp\\x.txt", "reg query HKLM\\x", "wmic volume list brief",
]
for c in BAD:
    assert dg.check(c), f"guard missed: {c}"
for c in GOOD:
    assert not dg.check(c), f"false positive: {c}"
for c in ('watch "' + "a " * 5000 + '"', "parallel '" + "x " * 5000 + "' ::: " + "a " * 2000, "del " + "C:\\*" * 3000, "Remove-Item -Recurse " + "-r " * 3000):
    t = time.time(); dg.check(c); assert time.time() - t < 1.0, "slow"
print("guard wave-5b regressions: ok")
