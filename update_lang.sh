#!/bin/bash

pybabel extract -F babel.cfg -o base.pot .
pybabel update -i base.pot -d translations
pybabel compile -f -d translations