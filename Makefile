PYTHON ?= .venv/bin/python

.PHONY: verify-hw05 verify-hw06 verify-hw07 test-hw07 verify-hw08 test-hw08

verify-hw05:
	@echo "Kazi Samina Maraj Mumu"
	@$(PYTHON) code/verify_hw05.py

verify-hw06:
	@echo "Kazi Samina Maraj Mumu"
	@$(PYTHON) code/verify_hw06.py

verify-hw07:
	@echo "Kazi Samina Maraj Mumu"
	@$(PYTHON) code/verify_hw07.py

test-hw07:
	@$(PYTHON) tests/test_hw07_auth.py
	@$(PYTHON) tests/test_hw07_agent.py
	@$(PYTHON) tests/test_hw07_tools.py
	@$(PYTHON) tests/test_hw07_bikeshare_check.py

verify-hw08:
	@echo "Kazi Samina Maraj Mumu"
	@$(PYTHON) code/verify_hw08.py

test-hw08:
	@$(PYTHON) tests/test_hw08.py
