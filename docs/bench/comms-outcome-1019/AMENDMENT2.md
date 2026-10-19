# Amendment A2 (2026-10-19), written while the first tune generation was running and before any tune arm output was scored

Finding: a unit test of the invented-figure guardrail showed bench.py collapses whitespace before it strips numbered-list markers, so the markers "1." and "2." of a numbered list were read as figures the notes lack, and a full weekday in the message was compared with an abbreviated one ("Thu") in the notes as a different day. Both would count a faithful message as inventing a figure, and numbered lists are the shape the arms differ in.

- fixed.py replaces bench._numbers (list markers removed first; weekdays compared by their three-letter prefix). bench.py stays frozen. Every report, the tests and the held-out run use `fixed.py report`.
- No tune arm output had been scored or read when this was decided. audit.py also calls bench.invented; its gold-field check is unaffected in practice (the 40 tune scenarios are re-audited under the fix, see the test).
