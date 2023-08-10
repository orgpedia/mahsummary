.DEFAULT_GOAL := help

GET_CAMPAIGNS_URL = 'https://listsrv.orgpedia.in/api/campaigns?page=1&per_page=100'
CAMPAIGNS_URL= 'https://listsrv.orgpedia.in/api/campaigns'


.PHONY: help htmlgen email rmCampaign install lint format check_env

help:
	$(info Please use 'make <target>', where <target> is one of)
	$(info )
	$(info   install     install packages and prepare software environment)
	$(info )
	$(info   htmlgen     generate html files based on new GRs
	$(info   email       send the markdown files via email
	$(info   rmCampaign  remove the earlier campaign
	$(info )
	$(info   lint        run the code linters)
	$(info   format      reformat code)
	$(info   pre-commit  run pre-commit checks, runs yaml lint, you need pre-commit)
	$(info )
	$(info Check the makefile to know exactly what each target is doing.)
	@echo # dummy command

install: pyproject.toml
	poetry install --only=dev

check_env:
ifndef GR_DIR
	$(error GR_DIR is undefined)
endif
ifndef LISTMONK_LOGIN
	$(error LISTMONK_LOGIN is undefined)
endif

htmlgen:
	python src/gen_summary.py $(GR_DIR) docs last en,mr

email: rmCampaign
	python run_campaign.py docs/en/dept

rmCampaign:
	@curl -vs -u $$(LISTMONK_LOGIN) -X GET $$(GET_CAMPAIGNS_URL) | jq '.data.results[].id' > /tmp/campaign.ids.txt 
	@for f in `cat /tmp/campaign.ids.txt`; do curl -u $$(LISTMONK_LOGIN) -X DELETE $$(CAMPAIGNS_URL)/$f; echo; done

lint:
	poetry run black -q .
	poetry run ruff .

format:
	poetry run black -q .
	poetry run ruff --fix .

export: readme
	poetry run op export-mah


# Use pre-commit if there are lots of edits,
# https://pre-commit.com/ for instructions
# Also set git hook `pre-commit install`
pre-commit:
	pre-commit run --all-files
