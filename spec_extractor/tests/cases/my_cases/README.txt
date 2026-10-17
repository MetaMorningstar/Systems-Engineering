YOUR OWN SCANS AS TEST CASES
============================

Put a scanned page or document here (PDF, TIFF, PNG, JPG) - for example a page the tool got wrong - and run,
from the spec_extractor folder:

    python tests/cases/run_cases.py --record tests/cases/my_cases/page12.pdf

That writes page12.pdf.expected.txt beside it, holding what the tool produces NOW. Open it in Notepad and
correct it to what the tool SHOULD produce (each line says what it is: requirement, tables, heading, document
...). From then on

    python tests/cases/run_cases.py --only MY

checks all of your own cases (and a plain run of run_cases.py checks them with the library's cases).

Nothing in this folder goes into git (see .gitignore here), and nothing is sent anywhere: the tool runs offline.
Everything the runs write for your scans - the tool's workbooks, the page images and text it keeps in _cache, and
the case reports, which quote the requirement text - is kept in the _results folder here, and nowhere else. When
a scan is no longer needed, delete it, its .expected.txt and the _results folder.
The full explanation, with an example, is in tests/README.md ("Adding your own example").
