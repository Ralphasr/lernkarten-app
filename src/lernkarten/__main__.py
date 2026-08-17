"""Enable ``python -m lernkarten`` as an alternative to the installed script."""

from lernkarten.cli import main

raise SystemExit(main())
