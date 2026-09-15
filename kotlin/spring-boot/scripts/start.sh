#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec java -jar build/libs/backend-template-0.0.1-SNAPSHOT.jar "$@"
