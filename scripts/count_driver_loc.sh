#!/bin/bash
# Script to count lines of code in each MongoDB driver repository, filtering by main code file types.
# Output: Driver name and total lines of code for relevant files.

declare -A repos=(
declare -A exts=(

set -e

# Parallel arrays for driver names, repo URLs, and extensions
drivers=(
  "C Driver"
  "C++ Driver"
  "C# Driver"
  "Go Driver"
  "Java Driver"
  "Node.js Driver"
  "PHP Driver"
  "Python Driver"
  "Ruby Driver"
  "Rust Driver"
)
repos=(
  "https://github.com/mongodb/mongo-c-driver.git"
  "https://github.com/mongodb/mongo-cxx-driver.git"
  "https://github.com/mongodb/mongo-csharp-driver.git"
  "https://github.com/mongodb/mongo-go-driver.git"
  "https://github.com/mongodb/mongo-java-driver.git"
  "https://github.com/mongodb/node-mongodb-native.git"
  "https://github.com/mongodb/mongo-php-library.git"
  "https://github.com/mongodb/mongo-python-driver.git"
  "https://github.com/mongodb/mongo-ruby-driver.git"
  "https://github.com/mongodb/mongo-rust-driver.git"
)
exts=(
  "c h"
  "cpp hpp h cc"
  "cs"
  "go"
  "java"
  "js ts"
  "php"
  "py"
  "rb"
  "rs"
)

echo "Driver,Lines of Code"

WORKDIR="mongo-drivers-loc-tmp"
rm -rf "$WORKDIR"
mkdir "$WORKDIR"
cd "$WORKDIR"

echo "Driver,Lines of Code"
for i in "${!drivers[@]}"; do
  driver="${drivers[$i]}"
  url="${repos[$i]}"
  ext_list="${exts[$i]}"
  repo_name=$(basename "$url" .git)
  git clone --depth 1 "$url" "$repo_name" > /dev/null 2>&1 || continue
  cd "$repo_name"
  # Build find command for relevant extensions
  find_args=()
  for ext in $ext_list; do
    find_args+=( -name "*.$ext" -o )
  done
  unset 'find_args[${#find_args[@]}-1]' # Remove trailing -o
  files=$(find . \( "${find_args[@]}" \))
  if [[ -n "$files" ]]; then
    loc=$(find . \( "${find_args[@]}" \) -print0 | xargs -0 cat | wc -l)
  else
    loc=0
  fi
  echo "$driver,$loc"
  cd ..
done

cd ..
rm -rf "$WORKDIR"
