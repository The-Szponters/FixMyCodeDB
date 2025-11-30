import hashlib
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import git
from pydriller import ModificationType, Repository

from scraper.config.config_utils import load_config


def calculate_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_scraper(config_path: str) -> None:
    logging.info(f"Starting scraper with config: {config_path}")

    config = load_config(config_path)
    if not config.repositories:
        logging.warning("No valid repositories found in config.")
        return

    for repo_config in config.repositories:
        process_repository(repo_config)


def get_git_content(repo: Any, commit_hash: str, file_path: str) -> str:
    try:
        return repo.git.show(f"{commit_hash}:{file_path}")
    except Exception:
        return ""


def get_all_repo_files(repo: Any, commit_hash: str) -> List[str]:
    try:
        return repo.git.ls_tree(
            "-r", "--name-only", commit_hash
        ).splitlines()
    except Exception:
        return []


def find_corresponding_file(
    base_file_path: str,
    target_extensions: List[str],
    all_repo_files: List[str]
) -> Optional[str]:
    base_dir = os.path.dirname(base_file_path)
    base_name = os.path.splitext(os.path.basename(base_file_path))[0]

    for ext in target_extensions:
        sibling_path = os.path.join(base_dir, base_name + ext)
        if sibling_path in all_repo_files:
            return sibling_path

    for file_path in all_repo_files:
        file_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(file_name)[0]
        file_ext = os.path.splitext(file_name)[1]

        if name_without_ext == base_name and file_ext in target_extensions:
            return file_path

    return None


def resolve_content(
    file_path: Optional[str],
    modified_map: Dict[str, Any],
    repo: Any,
    commit_hash: str
) -> Tuple[str, str]:
    if not file_path:
        return "", ""

    if file_path in modified_map:
        m = modified_map[file_path]
        return m.source_code_before or "", m.source_code or ""

    content = get_git_content(repo, commit_hash, file_path)
    return content, content


def find_class_name(modified_files: List[Any]) -> Optional[str]:
    for mod_file in modified_files:
        if not mod_file:
            continue
        for method in mod_file.changed_methods:
            if "::" in method.name:
                return method.name.split("::")[0]
    return None


def extract_class_block(content: str, class_name: str) -> str:
    if not content or not class_name:
        return content

    pattern = re.compile(rf"class\s+{class_name}\s*(?::[^\{{]*)?\{{")
    match = pattern.search(content)

    if not match:
        return content

    start_idx = match.start()
    brace_count = 0
    in_block = False
    end_idx = len(content)

    for i in range(start_idx, len(content)):
        if content[i] == "{":
            brace_count += 1
            in_block = True
        elif content[i] == "}":
            brace_count -= 1

        if in_block and brace_count == 0:
            end_idx = i + 1
            break

    return content[start_idx:end_idx] + ";"


def format_context(header: str, implementation: str) -> str:
    output = []
    if header.strip():
        output.append("[HEADER]")
        output.append(header.strip())
        output.append("[/HEADER]")

    if implementation.strip():
        output.append("[IMPLEMENTATION]")
        output.append(implementation.strip())
        output.append("[/IMPLEMENTATION]")

    return "\n".join(output)


def process_repository(repo_config: Any) -> None:
    logging.info(f"Processing repository: {repo_config.url}")

    since_dt = None
    if repo_config.start_date:
        since_dt = datetime.combine(
            repo_config.start_date, datetime.min.time()
        )

    to_dt = None
    if repo_config.end_date:
        to_dt = datetime.combine(repo_config.end_date, datetime.max.time())

    processed_count = 0
    try:
        repo_obj = Repository(repo_config.url, since=since_dt, to=to_dt)

        for commit in repo_obj.traverse_commits():
            if processed_count >= repo_config.target_record_count:
                logging.info(
                    f"Target record count reached for {repo_config.url}"
                )
                break

            if repo_config.fix_regexes:
                msg = commit.msg
                matched = False
                for pattern in repo_config.fix_regexes:
                    if re.search(pattern, msg, re.IGNORECASE | re.MULTILINE):
                        matched = True
                        break
                if not matched:
                    continue

            # Inicjalizacja obiektu repozytorium GitPython
            # commit.project_path wskazuje na lokalną ścieżkę do sklonowanego repo
            git_repo = git.Repo(commit.project_path)

            modified_map = {
                m.new_path: m for m in commit.modified_files if m.new_path
            }
            processed_bases: Set[str] = set()
            repo_files_cache: Optional[List[str]] = None

            for modified_file in commit.modified_files:
                path = modified_file.new_path
                if not path:
                    continue

                if modified_file.change_type == ModificationType.DELETE:
                    continue

                if "test" in path.lower():
                    continue

                if not path.endswith((".cpp", ".cxx", ".cc", ".h", ".hpp")):
                    continue

                filename = os.path.basename(path)
                base_name = os.path.splitext(filename)[0]

                if base_name in processed_bases:
                    continue

                processed_bases.add(base_name)

                # Użycie git_repo zamiast commit.repo
                if repo_files_cache is None:
                    repo_files_cache = get_all_repo_files(
                        git_repo, commit.hash
                    )

                header_path = None
                impl_path = None

                if path.endswith((".h", ".hpp")):
                    header_path = path
                    impl_path = find_corresponding_file(
                        path,
                        [".cpp", ".cxx", ".cc"],
                        repo_files_cache
                    )
                else:
                    impl_path = path
                    header_path = find_corresponding_file(
                        path,
                        [".h", ".hpp"],
                        repo_files_cache
                    )

                # Użycie git_repo zamiast commit.repo
                h_before, h_after = resolve_content(
                    header_path, modified_map, git_repo, commit.hash
                )
                cpp_before, cpp_after = resolve_content(
                    impl_path, modified_map, git_repo, commit.hash
                )

                files_in_pair = []
                if header_path and header_path in modified_map:
                    files_in_pair.append(modified_map[header_path])
                if impl_path and impl_path in modified_map:
                    files_in_pair.append(modified_map[impl_path])

                class_name = find_class_name(files_in_pair)

                if class_name:
                    h_before = extract_class_block(h_before, class_name)
                    h_after = extract_class_block(h_after, class_name)

                full_code_before = format_context(h_before, cpp_before)
                full_code_fixed = format_context(h_after, cpp_after)

                if full_code_before == full_code_fixed:
                    continue

                payload = {
                    "code_original": full_code_before,
                    "code_fixed": full_code_fixed,
                    "code_hash": calculate_hash(full_code_before),
                    "repo": {
                        "url": repo_config.url,
                        "commit_hash": commit.hash,
                        "commit_date": commit.committer_date.isoformat()
                    },
                    "ingest_timestamp": datetime.now().isoformat(),

                }

                # temporary function used for testing
                save_payload_to_file(payload=payload, output_dir="scraper_test_output")

                processed_count += 1
                logging.info(
                    f"[READY] extracted: {commit.hash[:7]} / {base_name}"
                )

    except Exception as e:
        logging.error(f"Error analyzing {repo_config.url}: {e}")


def save_payload_to_file(
    payload: Dict[str, Any],
    output_dir: str = "extracted_data"
) -> None:
    try:
        os.makedirs(output_dir, exist_ok=True)

        file_hash = payload.get("code_hash", "unknown_hash")
        filename = f"{file_hash}.json"
        filepath = os.path.join(output_dir, filename)

        readable_payload = payload.copy()

        if isinstance(readable_payload.get("code_original"), str):
            readable_payload["code_original"] = (
                readable_payload["code_original"].splitlines()
            )

        if isinstance(readable_payload.get("code_fixed"), str):
            readable_payload["code_fixed"] = (
                readable_payload["code_fixed"].splitlines()
            )

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(readable_payload, f, indent=4, ensure_ascii=False)

        logging.info(f"Saved payload to file: {filepath}")

    except Exception as e:
        logging.error(f"Failed to save payload locally: {e}")
