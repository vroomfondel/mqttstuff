.PHONY: tests help install venv lint dstart isort tcheck build commit-checks prepare pypibuild pypipush
SHELL := /usr/bin/bash
.ONESHELL:


help:
	@printf "\ninstall\n\tinstall requirements\n"
	@printf "\nisort\n\tmake isort import corrections\n"
	@printf "\nlint\n\tmake linter check with black\n"
	@printf "\ntcheck\n\tmake static type checks with mypy\n"
	@printf "\ntests\n\tLaunch tests\n"
	@printf "\nprepare\n\tLaunch tests and commit-checks\n"
	@printf "\ncommit-checks\n\trun pre-commit checks on all files\n"
	@printf "\pypibuild \n\tbuild image package for pypi\n"
	@printf "\pypipush \n\push package to pypi\n"
	@printf "\nbuild \n\tbuild docker image\n"
	@printf "\ndstart \n\tlaunch \"app\" in docker\n"




# check for "CI" not in os.environ || "GITHUB_RUN_ID" not in os.environ
venv_activated=if [ -z $${VIRTUAL_ENV+x} ] && [ -z $${GITHUB_RUN_ID+x} ] ; then printf "activating venv...\n" ; source .venv/bin/activate ; else printf "venv already activated or GITHUB_RUN_ID=$${GITHUB_RUN_ID} is set\n"; fi

install: venv

venv: .venv/touchfile

.venv/touchfile: requirements.txt requirements-dev.txt
	@if [ -z "$${GITHUB_RUN_ID}" ]; then \
		test -d .venv || python3.14 -m venv .venv; \
		source .venv/bin/activate; \
		pip install -r requirements-dev.txt; \
		touch .venv/touchfile; \
	else \
  		echo "Skipping venv setup because GITHUB_RUN_ID is set"; \
  	fi


tests: venv
	@$(venv_activated)
	pytest .

lint: venv
	@$(venv_activated)
	black -l 120 .

isort: venv
	@$(venv_activated)
	isort .

tcheck: venv
	@$(venv_activated)
	mypy *.py scripts mqttstuff mqttcommander


.git/hooks/pre-commit: venv
	@$(venv_activated)
	pre-commit install

commit-checks: .git/hooks/pre-commit
	@$(venv_activated)
	pre-commit run --all-files

prepare: tests commit-checks

mqttstuff_SOURCES := mqttcommander/*.py mqttstuff/*.py
VENV_DEPS := requirements.txt requirements-dev.txt requirements-build.txt

VERSION := $(shell egrep -m 1 ^version pyproject.toml | tr -s ' ' | tr -d '"' | tr -d "'" | tr -d " " | cut -d'=' -f2)

dist/mqttstuff-$(VERSION).tar.gz dist/mqttstuff-$(VERSION)-py3-none-any.whl dist/.touchfile: $(mqttstuff_mqttstuff) $(VENV_DEPS) pyproject.toml
	@$(venv_activated)
	rm -vf dist/mqttstuff-*
	pip install -r requirements-build.txt
	# pip install --upgrade twine build
	# python3 -m build
	# hatch version fix  # would bump version
	hatch build --clean
	@touch dist/.touchfile


pypibuild: venv dist/mqttstuff-$(VERSION).tar.gz dist/mqttstuff-$(VERSION)-py3-none-any.whl


dist/.touchfile_push: dist/mqttstuff-$(VERSION).tar.gz dist/mqttstuff-$(VERSION)-py3-none-any.whl
	@$(venv_activated)
	# python3 -m twine upload --repository pypi dist/mqttstuff-$(VERSION).tar.gz dist/mqttstuff-$(VERSION)-py3-none-any.whl
	hatch publish -r main
	@touch dist/.touchfile_push

pypipush: venv dist/.touchfile_push

build: venv
	./build.sh

dstart:
	# map config.local.yaml from current workdirectory into container
	docker run --network=host -it --rm --name mqttstuffephemeral -v $(pwd)/config.local.yaml:/app/config.local.yaml xomoxcc/mqttstuff:latest /bin/bash

# From https://hatch.pypa.io/latest/publish/#authentication
# HATCH_INDEX_USER and HATCH_INDEX_AUTH

# UPLOAD (old twine):
# python3 -m twine upload --repository testpypi dist/*

# UPLOAD to pypitest with hatch:
# hatch publish -r test

# UPLOAD to pypi(main) with hatch:
# hatch publish -r main

# INSTALL from test
# python3 -m pip install --index-url https://test.pypi.org/simple/ --no-deps example-package-YOUR-USERNAME-HERE

# INSTALL from test (if not found on pypitest -> install from normal pypi
# python3 -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ mqttstuff==0.0.1

# INSTALL from pypi(main)
# python3 -m pip install mqttstuff==0.0.1


