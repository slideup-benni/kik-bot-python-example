lint: dev_dependencies
	flake8 .

dev_dependencies:
	pip install --upgrade --requirement requirements.dev.txt

dependencies:
	pip install --upgrade --requirement requirements.txt

test: dependencies lint
	nosetests --with-coverage
.PHONY: test lint dependencies dist dev_dependencies
