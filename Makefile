# Shortcuts. Production uses .env, preprod uses .env.preprod (ENV=preprod).
ENVFILE := $(if $(filter preprod,$(ENV)),.env.preprod,.env)
RUN := set -a && . ./$(ENVFILE) && set +a && .venv/bin/python manage.py
DOMAIN ?= data.education.gouv.fr

test:            ## all tests (local stand, uses .env so graph tests can write)
	set -a && . ./.env && set +a && .venv/bin/python manage.py test
eval:            ## A/B/C on the legacy set (ENV=preprod recommended)
	$(RUN) eval $(DOMAIN) --mode abc --suite education
eval-holdout:    ## A/B/C on the locked holdout of the v2 set
	$(RUN) eval $(DOMAIN) --mode abc --suite education_v2 --split holdout
check:           ## deterministic optimizer checks, no model
	$(RUN) optimizer_check $(DOMAIN)
traces:          ## record the demo scenarios (calls the model)
	$(RUN) record_traces $(DOMAIN)
lab:             ## one AutoContext Lab cycle (refuses outside preprod)
	set -a && . ./.env.preprod && set +a && .venv/bin/python manage.py lab run $(DOMAIN)
demo:            ## build the preprod showcase and (re)start the preprod containers
	set -a && . ./.env.preprod && set +a && .venv/bin/python manage.py build_site $(DOMAIN) site-preprod
	docker compose -f docker-compose.preprod.yml up -d --build
.PHONY: test eval eval-holdout check traces lab demo
