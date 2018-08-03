#!/bin/bash

pybabel extract -F babel.cfg -o base.pot .
# pybabel update -i base.pot -d translations # will be done by crowdin
pybabel compile -f -d translations