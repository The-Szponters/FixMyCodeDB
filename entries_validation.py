import json
import random
import os
import subprocess
import sys
import csv
from datetime import datetime
from pathlib import Path

# Konfiguracja
DATA_FOLDER = "data_for_import"
LABELS_CONFIG = "scraper/labels_config.json"
RESULTS_FILE = "validation_stats.csv"
NUMBER_OF_ENTRIES = 50
SEED = 42
OUTPUT_CPP_DIR = "validation_cpp_files"


def setup_output_dir():
    """Tworzy folder na pliki .cpp jeśli nie istnieje."""
    Path(OUTPUT_CPP_DIR).mkdir(exist_ok=True, parents=True)


def cleanup_output_dir():
    """Usuwa pliki tymczasowe z folderu output."""
    for file in Path(OUTPUT_CPP_DIR).glob("*"):
        file.unlink()


def get_target_groups():
    """Pobiera listę grup etykiet z pliku konfiguracyjnego."""
    try:
        with open(LABELS_CONFIG, "r", encoding="utf-8") as f:
            config = json.load(f)
            return list(config.get("error_classification", {}).keys())
    except Exception as e:
        print(f"Warning: Could not read labels config ({e}). Using default groups.")
        return [
            "memory_management",
            "invalid_access",
            "uninitialized",
            "concurrency",
            "logic_error",
            "resource_leak",
            "security_portability",
            "unused_code",
            "const_correctness",
            "redundant_code",
            "stl_misuse",
            "class_design",
            "code_style",
        ]


def select_files(data_path, target_groups, missing_stats_file):
    """Wybiera pliki tak, aby pokryć każdą grupę, a potem dopełnia losowo."""
    all_files = list(data_path.glob("*.json"))
    if not all_files:
        return []

    # Mapowanie grupa -> lista plików
    files_by_group = {group: [] for group in target_groups}
    all_files_map = {f.name: f for f in all_files}

    # Skanowanie plików (może być wolne przy dużej ilości, ale tu mamy limit 50 w założeniu wynikowym, plików w folderze może być więcej)
    # Optymalizacja: wczytujemy tylko labels
    print("Scanning files for labels coverage...")

    file_labels_map = {}  # filename -> set of groups

    for f_path in all_files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                groups = data.get("labels", {}).get("groups", {})
                active_groups = [k for k, v in groups.items() if v]
                file_labels_map[f_path.name] = set(active_groups)

                for g in active_groups:
                    if g in files_by_group:
                        files_by_group[g].append(f_path)
        except Exception:
            continue

    selected_files = set()
    missing_groups = []

    # 1. Wybierz po jednym dla każdej grupy
    for group in target_groups:
        candidates = files_by_group.get(group, [])
        if not candidates:
            missing_groups.append(group)
            continue

        # Wybieramy losowy z kandydatów, który jeszcze nie był wybrany, jeśli to możliwe
        # Sortowanie dla determinizmu przed shuffle (seed jest ustawiony w main)
        candidates.sort(key=lambda x: x.name)
        random.shuffle(
            candidates
        )  # shuffle w miejscu używając globalnego random z seedem

        chosen = None
        for cand in candidates:
            if cand not in selected_files:
                chosen = cand
                break

        if not chosen:
            # Wszystkie kandydujące już wybrane, bierzemy pierwszy
            chosen = candidates[0]

        selected_files.add(chosen)

    # Logowanie brakujących grup
    if missing_groups:
        msg = f"No entries found for labels: {', '.join(missing_groups)}"
        print(f"\n[!] {msg}")
        with open(missing_stats_file, "a", encoding="utf-8") as f:
            f.write(f"# {datetime.now().isoformat()} - {msg}\n")
    else:
        print("[+] All label groups covered.")

    # 2. Dopełnij do NUMBER_OF_ENTRIES
    needed = NUMBER_OF_ENTRIES - len(selected_files)
    if needed > 0:
        remaining_files = [f for f in all_files if f not in selected_files]
        if len(remaining_files) <= needed:
            selected_files.update(remaining_files)
        else:
            remaining_files.sort(key=lambda x: x.name)
            selected_files.update(random.sample(remaining_files, needed))

    # Konwersja na listę i ponowne przemieszanie, żeby nie analizować grupami
    final_list = list(selected_files)
    final_list.sort(key=lambda x: x.name)
    random.shuffle(final_list)

    return final_list[:NUMBER_OF_ENTRIES]


def run_cppcheck(file_path):
    """Uruchamia cppcheck na podanym pliku i zwraca output."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} does not exist."

    try:
        # Używamy --enable=all, aby zobaczyć wszystkie ostrzeżenia
        result = subprocess.run(
            ["cppcheck", "--enable=all", "--inline-suppr", str(file_path)],
            capture_output=True,
            text=True,
        )
        return result.stderr + result.stdout
    except FileNotFoundError:
        return "Error: cppcheck command not found. Please install cppcheck."
    except Exception as e:
        return f"Error running cppcheck: {e}"


def save_result(entry_id, is_valid, file_name, groups):
    """Dopisuje wynik walidacji do pliku CSV."""
    file_exists = os.path.isfile(RESULTS_FILE)

    with open(RESULTS_FILE, "a", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["timestamp", "entry_id", "file_name", "is_valid", "groups"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp": datetime.now().isoformat(),
                "entry_id": entry_id,
                "file_name": file_name,
                "is_valid": "VALID" if is_valid else "INVALID",
                "groups": ",".join(groups),
            }
        )


import re


def parse_cppcheck_output(output):
    """Parses cppcheck output to extract unique error IDs."""
    errors = set()
    # Matches strings in brackets like [unusedFunction]
    matches = re.findall(r"\[([a-zA-Z0-9_]+)\]", output)
    for match in matches:
        if match != "missingInclude":
            errors.add(match)
    # Sort for consistent output
    return sorted(list(errors))


def process_file(json_file):
    """Przetwarza pojedynczy plik JSON."""
    cleanup_output_dir()

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to read {json_file}: {e}")
        return

    # Pobierz dane z JSON
    entry_id = data.get("_id", json_file.stem)
    code_original = data.get("code_original", "")
    code_fixed = data.get("code_fixed", "")
    labels = data.get("labels", {})

    print("\n" + "=" * 80)
    print(f"File: {json_file.name}")
    print(f"Entry ID: {entry_id}")

    # Wyświetl etykiety z JSON
    groups = labels.get("groups", {})
    active_groups = [k for k, v in groups.items() if v]
    cppcheck_labels_json = labels.get("cppcheck", [])

    print("-" * 20 + " JSON LABELS " + "-" * 20)
    print(f"Groups: {', '.join(active_groups) if active_groups else 'None'}")
    print(
        f"Cppcheck (saved in DB): {', '.join(cppcheck_labels_json) if cppcheck_labels_json else 'None'}"
    )

    # Zapisz pliki C++
    original_path = Path(OUTPUT_CPP_DIR) / f"{entry_id}_original.cpp"
    fixed_path = Path(OUTPUT_CPP_DIR) / f"{entry_id}_fixed.cpp"

    with open(original_path, "w", encoding="utf-8") as f:
        f.write(code_original)

    # Uruchom cppcheck na oryginale
    print("-" * 20 + " ACTIVE CPPCHECK ANALYSIS " + "-" * 20)
    print(f"Analyzing Original Code ({original_path})...")
    output_original = run_cppcheck(original_path)
    # Parse and print errors
    errors_original = parse_cppcheck_output(output_original)
    if errors_original:
        print(f"Detected Errors: {', '.join(errors_original)}")
        # Optional: Print raw output if needed, but request asked to just show errors
        # print(output_original.strip())
    else:
        print("Detected Errors: None")

    if code_fixed:
        with open(fixed_path, "w", encoding="utf-8") as f:
            f.write(code_fixed)

        print(f"\nAnalyzing Fixed Code ({fixed_path})...")
        output_fixed = run_cppcheck(fixed_path)
        # Parse and print errors
        errors_fixed = parse_cppcheck_output(output_fixed)
        if errors_fixed:
            print(f"Detected Errors: {', '.join(errors_fixed)}")
        else:
            print("Detected Errors: None")
    else:
        print("\nNo Fixed Code available in this entry.")

    print("=" * 80)

    # User Input
    while True:
        choice = input("Is this entry VALID? (y/n): ").strip().lower()
        if choice in ["y", "yes"]:
            save_result(entry_id, True, json_file.name, active_groups)
            break
        elif choice in ["n", "no"]:
            save_result(entry_id, False, json_file.name, active_groups)
            break
        else:
            print("Invalid input. Please enter 'y' or 'n'.")


def main():
    setup_output_dir()
    cleanup_output_dir()  # Clean start

    # Ustaw seed dla powtarzalności
    random.seed(SEED)

    data_path = Path(DATA_FOLDER)
    if not data_path.exists():
        print(f"Error: Folder '{DATA_FOLDER}' does not exist.")
        return

    # Pobierz oczekiwane grupy
    target_groups = get_target_groups()
    print(f"Targeting {len(target_groups)} label groups.")

    # Wybierz pliki
    selected_files = select_files(data_path, target_groups, RESULTS_FILE)
    count = len(selected_files)

    print(f"\nSelected {count} files for validation (Seed: {SEED}).")
    print(f"Results will be appended to '{RESULTS_FILE}'.")
    print("Interactive mode started. Press Ctrl+C to exit anytime.")

    try:
        for i, file_path in enumerate(selected_files):
            input(
                f"\n[Progress: {i}/{count}] Press Enter to process next file (or Ctrl+C to stop)..."
            )
            process_file(file_path)

        print("\nValidation complete.")
        cleanup_output_dir()  # Cleanup at the end

    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Exiting.")
        cleanup_output_dir()


if __name__ == "__main__":
    main()
