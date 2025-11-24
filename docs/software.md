# Metodyka tworzenia kodu

W projekcie przyjmujemy prosty, ale uporządkowany workflow oparty na
**feature branchach**, zbliżony do GitHub Flow.\
Kluczową zasadą jest **brak bezpośrednich pushy na gałąź `main`** --
wszelkie zmiany trafiają na `main` wyłącznie poprzez **Pull Requesty**
po **code review** i przejściu **CI**.

## Struktura gałęzi

### `main`

-   zawsze zawiera wersję nadającą się do „wydania" -- kod buduje się,
    testy przechodzą, pipeline CI jest zielony;
-   gałąź jest chroniona:
    -   brak możliwości bezpośredniego pusha,
    -   wymagany Merge Request i co najmniej jedna akceptacja
        recenzenta.

### Gałęzie funkcjonalne (`feature/*`)

-   tworzone z `main` dla każdej zmiany lub niewielkiego zestawu
    powiązanych zadań, np.:
    -   `feature/cicd`
    -   `feature/extract-bug-fix-pairs`
    -   `feature/db-statistics-endpoint`
-   po zakończeniu pracy i zmergowaniu do `main`, gałąź jest usuwana,
    aby utrzymać porządek w repozytorium.



# Poprawny i uargumentowany wybór języków programowania

## Wybór języka

Do implementacji narzędzi tworzących bazę danych oraz narzędzi analizy
danych w projekcie zostanie wykorzystany język **Python**.

## Zgodność z charakterem problemu

Problem, który rozwiązujemy, obejmuje przede wszystkim:

1.  **Ekstrakcję danych z repozytoriów** (Firefox, CPython, PostgreSQL
    itp.) -- praca z Gitem, historią commitów, diffami.\
2.  **Przetwarzanie tekstu/kodu źródłowego** -- wyszukiwanie fragmentów
    C++, parsowanie, analiza różnic między wersjami plików.\
3.  **Budowę i utrzymanie bazy danych** -- tworzenie rekordów,
    zapisywanie statystyk, wykonywanie podstawowych zapytań
    analitycznych.\
4.  **Analizę i eksplorację danych** -- zliczanie typów błędów,
    tworzenie zestawień, przygotowanie danych do uczenia maszynowego.\
5.  **Eksport danych** -- dostarczenie danych w formacie nadającym się
    do trenowania modeli ML.

Zadania te mają charakter skryptowy, wymagają pracy z dużą liczbą
plików, analizą danych i automatyzacją --- co doskonale pokrywa się z
profilem Pythona.

## Zalety Pythona w tym projekcie

### 1. Bogaty ekosystem do pracy z repozytoriami i kodem

-   Biblioteki takie jak **GitPython** czy **PyDriller** ułatwiają:
    -   iterację po commitach i gałęziach,
    -   pobieranie diffów i metadanych,
    -   filtrowanie zmian dotyczących plików C++.
-   Istnieją wiązania do parserów C++ (np. **libclang**) oraz biblioteki
    oparte na **tree-sitter**, umożliwiające analizę składniową kodu.

### 2. Wygodne przetwarzanie tekstu i danych

-   Python oferuje bogate narzędzia pracy na dowolnych strukturach
    tekstu i plików.\
-   Biblioteki takie jak **pandas** umożliwiają szybką eksplorację
    danych, raportowanie oraz agregację statystyk błędów.

### 3. Integracja z bazami danych

-   Python posiada wsparcie dla baz relacyjnych i nierelacyjnych
    (PostgreSQL, SQLite, MySQL, MongoDB).\
-   Ułatwia to:
    -   definiowanie struktury rekordów,\
    -   wstawianie i aktualizowanie danych,\
    -   wykonywanie złożonych zapytań analitycznych.

### 4. Wsparcie dla uczenia maszynowego

-   Python jest dominującym językiem ML --- biblioteki takie jak
    **scikit-learn**, **PyTorch**, **TensorFlow**, **transformers**
    ułatwiają pracę na danych.\
-   Wykorzystanie Pythona już na etapie ekstrakcji pozwoli zachować
    spójność całego pipeline'u danych.

### 5. Szybkość prototypowania i czytelność

-   Python pozwala szybko tworzyć prototypy i płynnie przechodzić do
    pełnych modułów.\
-   Jego składnia ułatwia code review i współpracę zespołową.

### 6. Możliwość optymalizacji krytycznych fragmentów

-   Python umożliwia korzystanie z modułów napisanych w C/C++ lub
    optymalizowanych bibliotek --- bez utraty elastyczności.

## Alternatywy i ich ocena

### C++

-   Wolniejsze prototypowanie, trudniejsze zarządzanie zależnościami.
-   Nadaje się głównie do fragmentów wymagających wysokiej wydajności.

### Java / Kotlin / C

-   Mocne w backendzie, słabsze w ML i szybkiej analizie danych.

### Bash, Perl

-   Mało czytelne, słabo skalują się w dużych projektach.

## Podsumowanie

Python: - najlepiej wspiera charakter projektu, - integruje się z ML, -
umożliwia tworzenie czytelnego, modularnego, testowalnego kodu.


# Architektura systemu i wykorzystywane technologie

System FixMyCodeDB został zaprojektowany jako mikrousługowa aplikacja konteneryzowana, składająca się z czterech głównych komponentów współpracujących ze sobą poprzez API REST oraz wspólną bazę danych.

## Komponenty systemu

### 1. MongoDB (Baza danych)

**Technologia:** MongoDB 8.x w kontenerze Docker

**Zadania:**
-   przechowywanie rekordów zawierających pary `code_original` i `code_fixed`
-   przechowywanie metadanych repozytoriów (URL, commit hash, data commitu)
-   przechowywanie etykiet błędów z różnych narzędzi analizy statycznej
-   wsparcie dla złożonych zapytań i filtrowania danych

**Wybór technologii:**
-   MongoDB jako NoSQL doskonale radzi sobie z przechowywaniem półstrukturalnych danych (fragmenty kodu mogą mieć różną długość i strukturę)
-   Schemat dokumentowy pozwala na elastyczne rozszerzanie etykiet bez konieczności migracji
-   Natywne wsparcie dla indeksowania zagnieżdżonych dokumentów ułatwia wyszukiwanie po etykietach

### 2. FastAPI (Backend API)

**Technologia:** FastAPI 0.121+ z Pydantic, Motor (async MongoDB driver), Uvicorn

**Zadania:**
-   udostępnianie REST API do operacji CRUD na rekordach
-   walidacja danych wejściowych za pomocą modeli Pydantic
-   zaawansowane filtrowanie i sortowanie rekordów
-   endpoint do eksportu danych w formacie JSON

**Wybór technologii:**
-   FastAPI oferuje automatyczną dokumentację API (Swagger/OpenAPI)
-   Asynchroniczne przetwarzanie zapytań (Motor + async/await) zwiększa wydajność
-   Pydantic zapewnia silne typowanie i walidację danych
-   Minimalna ilość boilerplate code przyspiesza rozwój

**Kluczowe endpointy:**
-   `POST /entries/` - dodawanie nowego rekordu
-   `GET /entries/{id}` - pobranie rekordu po ID
-   `GET /entries/` - lista wszystkich rekordów
-   `PUT /entries/{id}` - aktualizacja rekordu
-   `DELETE /entries/{id}` - usunięcie rekordu
-   `POST /entries/query/` - zaawansowane filtrowanie z parametrami sort/limit

### 3. Scraper (Ekstraktor danych z repozytoriów)

**Technologia:** Python 3.12, PyDriller, GitPython

**Zadania:**
-   klonowanie i analiza repozytoriów Git projektów C++
-   filtrowanie commitów zawierających poprawki błędów (regex na komunikaty commitów: "fix", "bug", "patch" itp.)
-   ekstrakcja par `code_original` i `code_fixed` z diffów
-   wysyłanie przetworzonych danych do FastAPI

**Planowane biblioteki:**
-   **PyDriller** - iteracja po commitach, pobieranie diffów, filtrowanie po rozszerzeniach plików (.cpp, .h, .cc)
-   **GitPython** - niskopoziomowe operacje na repozytoriach Git
-   **tree-sitter** lub **libclang** - parsowanie składni C++ do ekstrakcji funkcji/bloków kodu

### 4. CLI (Narzędzie konsolowe)

**Technologia:** Python 3.12, Typer/Click, httpx

**Zadania:**
-   interaktywny interfejs dla użytkownika końcowego
-   przeglądanie, filtrowanie i wyszukiwanie rekordów
-   ręczne dodawanie i edycja rekordów
-   eksport danych do plików CSV/JSON
-   wywoływanie scrapera dla nowych repozytoriów

**Planowane funkcjonalności:**
```bash
fixmycode list --labels memory_errors --limit 50
fixmycode add --file buggy.cpp --fixed fixed.cpp
fixmycode export --format json --output dataset.json
fixmycode scrape --repo https://github.com/mozilla/firefox
```

## Narzędzia analizy statycznej kodu

Projekt wykorzystuje narzędzia do automatycznego etykietowania błędów:

### cppcheck
-   detekcja memory leaks, null pointer dereference, buffer overflow
-   etykiety zapisywane w `labels.cppcheck`

### clang-tidy
-   sprawdzanie zgodności z modernymi standardami C++
-   detekcja undefined behavior, performance issues
-   etykiety zapisywane w `labels.clang`

### Grupowanie etykiet
Etykiety są dodatkowo agregowane w kategorie:
-   `memory_errors` - wycieki pamięci, nieprawidłowe dealokacje
-   `undefined_behavior` - niezdefiniowane zachowanie wg. standardu C++
-   `correctness` - logiczne błędy kodu
-   `performance` - nieoptymalne użycie zasobów
-   `style` - problemy z formatowaniem i konwencjami

## Konteneryzacja i orkiestracja

**Technologia:** Docker, Docker Compose

Wszystkie komponenty są konteneryzowane dla zapewnienia:
-   izolacji środowiskowej i powtarzalności buildów
-   prostego deploymentu na różnych platformach
-   możliwości skalowania poszczególnych usług

**docker-compose.yaml** definiuje:
-   sieć `backend` dla komunikacji między kontenerami
-   volume `mongo_data` dla persistence bazy danych
-   zmienne środowiskowe (MONGO_URI, API_URL)
-   zależności między kontenerami (depends_on)

## Potencjalne zastosowanie w ML

System jest przygotowany do wykorzystania w trenowaniu modeli transformerowych:

### Przygotowanie danych
-   eksport par `code_original` → `code_fixed` jako dane treningowe
-   filtrowanie po etykietach dla zadań specyficznych (np. tylko memory errors)
-   tokenizacja za pomocą tokenizera z modelu CodeBERT/GraphCodeBERT

### Możliwe zadania ML
-   **Bug Classification** - klasyfikacja typu błędu na podstawie buggy code
-   **Code Repair** - generowanie poprawionego kodu (seq2seq)
-   **Bug Detection** - detekcja, czy fragment kodu zawiera błąd
-   **Fine-tuning** - dostrajanie pretrenowanych modeli (CodeBERT, CodeT5, StarCoder)

### Przykładowe modele
-   **CodeBERT** (Microsoft) - encoder do reprezentacji kodu
-   **GraphCodeBERT** - uwzględnia strukturę AST
-   **CodeT5** - model seq2seq do naprawy kodu
-   **StarCoder** - duży model generatywny dla kodu

# Pipeline CI/CD

Projekt wykorzystuje **GitHub Actions** do automatyzacji testowania i kontroli jakości kodu.

## Konfiguracja CI

Plik `.github/workflows/ci.yml` definiuje pipeline uruchamiany przy:
-   każdym pushu na gałąź `main`
-   każdym Pull Requeście

### Kroki pipeline'u

**1. Checkout kodu**
```yaml
uses: actions/checkout@v4
```
Pobiera kod źródłowy z repozytorium

**2. Konfiguracja środowiska Python**
```yaml
uses: actions/setup-python@v5
with:
  python-version: '3.12'
```
Ustawia Python 3.12 jako interpreter

**3. Instalacja zależności**
```bash
pip install -r requirements.txt
pip install -r cli/requirements.txt
pip install -r scraper/requirements.txt
pip install -r fastapi_app/requirements.txt
```
Instaluje wszystkie wymagane biblioteki dla każdego komponentu

**4. Analiza jakości kodu - flake8**
```bash
flake8 cli fastapi_app scraper
```
Sprawdza:
-   zgodność z PEP 8 (style guide)
-   zbyt długie linie
-   nieużywane importy
-   złożoność cyklometryczną funkcji

**5. Analiza bezpieczeństwa - bandit**
```bash
bandit -r cli fastapi_app scraper
```
Skanuje kod pod kątem:
-   użycia niebezpiecznych funkcji (eval, exec)
-   słabych algorytmów kryptograficznych
-   potencjalnych SQL injection (choć używamy MongoDB)
-   hardcodowanych sekretów

## Polityka mergowania

Zgodnie z metodologią GitHub Flow:
-   **PR nie może być zmergowany**, jeśli pipeline CI jest czerwony
-   wymagane jest **code review** od co najmniej jednego członka zespołu
-   po zaakceptowaniu i przejściu CI, PR jest mergowany do `main`
-   feature branch jest następnie usuwany

## Przyszłe rozszerzenia CI/CD

W kolejnych iteracjach planowane jest dodanie:

### Testy jednostkowe i integracyjne
-   pytest dla modułów Python
-   testy API FastAPI (TestClient)
-   testy integracyjne z testową instancją MongoDB

### Build i push obrazów Docker
-   automatyczne budowanie obrazów Docker po zmergowaniu do `main`
-   tagowanie obrazów (latest, git commit SHA)
-   publikacja w GitHub Container Registry lub Docker Hub

### Deploy do środowiska staging/prod
-   automatyczny deploy na serwer testowy po CI
-   ręczna akceptacja przed deployem na produkcję

# Minimum Viable Product (MVP)

Funkcjonalne, kompletne narzędzie CLI, które obejmuje implementację
kluczowych wymagań **"MUST"** i realizuje podstawowe scenariusze
zdefiniowanych przypadków użycia.

-   System filtruje commity wskazanego repozytorium, przygotowuje pary
    **code_buggy** i **code_fixed** oraz wstawia je jako rekordy do bazy
    danych
-   System półautomatycznie przypisuje rekordom etykiety błędów za
    pomocą narzędzi analizy statystycznej
-   System umożliwia ręczne przypisanie, edycję etykiet dla rekordów,
    ręczne dodawanie rekordów
-   System umożliwia przeglądanie i filtrowanie zebranych rekordów
-   System umożliwia eksport rekordów do JSON/CSV

# Testy akceptacyjne

Testy akceptacyjne weryfikują realizację kluczowych scenariuszy użycia systemu FixMyCodeDB, obejmując pełny cykl życia danych - od ekstrakcji z repozytoriów, przez etykietowanie, aż do wykorzystania w modelach ML.

## TA-1: Ekstrakcja danych z repozytorium Git

**Scenariusz:**\
Użytkownik uruchamia scraper dla nowego repozytorium C++, system analizuje historię commitów i zapisuje poprawki błędów w bazie.

**Kroki:**
1. Uruchomienie scrapera z URL repozytorium: `fixmycode scrape --repo https://github.com/project/repo`
2. System klonuje repozytorium i iteruje po commitach
3. Filtrowanie commitów po regex: `(fix|bug|patch|repair|correct)` w wiadomości
4. Ekstrakcja diffów dla plików `.cpp`, `.h`, `.cc`
5. Utworzenie rekordów z polami:
   - `code_original` - kod przed poprawką
   - `code_fixed` - kod po poprawce
   - `repo.url`, `repo.commit_hash`, `repo.commit_date`
   - `code_hash` - SHA256 hash kodu dla deduplikacji
   - `ingest_timestamp` - czas przetworzenia

**Kryteria akceptacji:**
-   co najmniej 10 rekordów zostaje zapisanych w bazie dla repozytorium z >100 commitami
-   pole `code_hash` jest unikalne - duplikaty nie są dodawane ponownie
-   dla każdego rekordu `code_original != code_fixed`
-   metadane `repo.*` są poprawnie wypełnione
-   weryfikacja poprzez `GET /entries/` zwraca nowe rekordy

## TA-2: Automatyczne etykietowanie błędów

**Scenariusz:**\
System automatycznie analizuje zapisane w bazie fragmenty `code_original` za pomocą narzędzi analizy statycznej i przypisuje etykiety błędów.

**Kroki:**
1. Wybór nieoznakowanych rekordów z bazy: `labels.cppcheck == {}`
2. Zapisanie `code_original` do pliku tymczasowego
3. Uruchomienie `cppcheck --enable=all --xml` na fragmencie
4. Parsowanie raportu XML i ekstrakcja kategorii błędów
5. Uruchomienie `clang-tidy` z odpowiednimi checkami
6. Mapowanie błędów na grupy: `memory_errors`, `undefined_behavior`, `correctness`, `performance`, `style`
7. Aktualizacja rekordu w bazie: `PUT /entries/{id}`

**Kryteria akceptacji:**
-   co najmniej 80% rekordów z błędami otrzymuje etykiety `labels.cppcheck`
-   dla błędów memory leak etykieta `labels.groups.memory_errors == 1`
-   dla błędów null pointer etykieta `labels.groups.correctness == 1`
-   etykiety są zapisane jako binary flags (0/1) zgodnie z modelem Pydantic
-   możliwość filtrowania: `POST /entries/query/ {"filter": {"labels.groups.memory_errors": 1}}`

## TA-3: Interaktywne CLI - przeglądanie i filtrowanie

**Scenariusz:**\
Użytkownik wykorzystuje narzędzie CLI do eksploracji bazy danych, wyszukiwania rekordów według kryteriów oraz podglądu par kod błędny/poprawny.

**Kroki:**
1. Wylistowanie wszystkich rekordów: `fixmycode list`
2. Filtrowanie po etykiecie: `fixmycode list --labels memory_errors --limit 20`
3. Filtrowanie po repozytorium: `fixmycode list --repo firefox`
4. Wyświetlenie szczegółów rekordu: `fixmycode show <id>`
5. Podgląd diff (side-by-side): `fixmycode diff <id>`

**Kryteria akceptacji:**
-   `fixmycode list` zwraca tabelę z kolumnami: ID, repo, commit_hash, labels
-   filtrowanie `--labels` zawęża wyniki tylko do rekordów z daną etykietą
-   `fixmycode show <id>` wyświetla pełne pole `code_original` i `code_fixed`
-   `fixmycode diff <id>` pokazuje kolorowy diff (czerwony/zielony) z użyciem difflib
-   obsługa błędów: wyświetlenie komunikatu jeśli API jest niedostępne

## TA-4: Eksport danych do formatu ML

**Scenariusz:**\
Użytkownik eksportuje przefiltrowane rekordy do formatu JSON/CSV nadającego się do użycia jako dataset treningowy dla modeli transformerowych.

**Kroki:**
1. Eksport wszystkich rekordów: `fixmycode export --format json --output dataset.json`
2. Eksport przefiltrowany: `fixmycode export --labels memory_errors --format csv --output memory_bugs.csv`
3. Weryfikacja struktury pliku JSON:
   ```json
   [
     {
       "id": "...",
       "code_original": "...",
       "code_fixed": "...",
       "labels": {"groups": {"memory_errors": 1, ...}},
       "repo": {"url": "...", "commit_hash": "..."}
     }
   ]
   ```

**Kryteria akceptacji:**
-   format JSON zawiera wszystkie pola modelu `CodeEntry`
-   format CSV zawiera kolumny: id, code_original, code_fixed, memory_errors, undefined_behavior, correctness, performance, style, repo_url
-   plik JSON jest poprawny syntaktycznie (można załadować przez `json.load()`)
-   dla 1000 rekordów plik jest generowany w czasie <10 sekund
-   znaki specjalne w kodzie C++ (cudzysłowy, backslashe) są prawidłowo escape'owane

## TA-5: Ręczne zarządzanie rekordami

**Scenariusz:**\
Użytkownik ręcznie dodaje nowy rekord (np. z własnego projektu) oraz edytuje istniejący rekord aby poprawić etykiety lub kod.

**Kroki:**
1. Dodanie nowego rekordu:
   ```bash
   fixmycode add \
     --original "int* p = nullptr; *p = 5;" \
     --fixed "int* p = new int; *p = 5; delete p;" \
     --label memory_errors
   ```
2. Edycja etykiet istniejącego rekordu:
   ```bash
   fixmycode edit <id> --add-label undefined_behavior
   ```
3. Edycja kodu:
   ```bash
   fixmycode edit <id> --set-fixed "int* p = std::make_unique<int>(5);"
   ```
4. Usunięcie rekordu:
   ```bash
   fixmycode delete <id>
   ```

**Kryteria akceptacji:**
-   `fixmycode add` tworzy nowy rekord w bazie i zwraca jego ID
-   dla ręcznie dodanych rekordów `repo.url == "manual"`
-   `fixmycode edit` aktualizuje tylko podane pola, reszta pozostaje bez zmian
-   walidacja: nie można zapisać `code_original == code_fixed`
-   `fixmycode delete` usuwa rekord z bazy, potwierdzenie: "Record <id> deleted"

## TA-6: Przygotowanie datasetu do treningu transformera

**Scenariusz:**\
Badacz ML eksportuje dane z bazy i używa ich do fine-tuningu modelu CodeBERT na zadaniu klasyfikacji błędów w kodzie C++.

**Kroki:**
1. Eksport danych treningowych:
   ```bash
   fixmycode export --format json --min-length 50 --max-length 512 --output train.json
   ```
2. Załadowanie danych w skrypcie Python:
   ```python
   import json
   from transformers import AutoTokenizer

   with open("train.json") as f:
       data = json.load(f)

   tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")

   # Tokenizacja buggy code
   inputs = [entry["code_original"] for entry in data]
   labels = [entry["labels"]["groups"]["memory_errors"] for entry in data]

   tokenized = tokenizer(inputs, padding=True, truncation=True, max_length=512)
   ```
3. Trening klasyfikatora binarnego (memory_errors: 0/1):
   ```python
   from transformers import AutoModelForSequenceClassification, Trainer, TrainingArguments

   model = AutoModelForSequenceClassification.from_pretrained(
       "microsoft/codebert-base",
       num_labels=2
   )

   training_args = TrainingArguments(
       output_dir="./results",
       num_train_epochs=3,
       per_device_train_batch_size=8,
       evaluation_strategy="epoch"
   )

   # ... przygotowanie Dataset, Trainer.train()
   ```
4. Ewaluacja na zbiorze testowym z bazy

**Kryteria akceptacji:**
-   eksportowane rekordy mają długość kodu w zakresie 50-512 tokenów (filtr `--min-length`, `--max-length`)
-   proporcja klas jest zbalansowana (50±10% rekordów z memory_errors=1)
-   tokenizacja CodeBERT nie zwraca błędów na eksportowanych fragmentach
-   po 3 epokach treningu model osiąga accuracy >70% na zbiorze testowym
-   struktura JSON jest kompatybilna z `datasets.load_dataset("json", data_files="train.json")`
-   możliwość eksportu w formacie train/val/test split:
   ```bash
   fixmycode export --split train:0.7,val:0.15,test:0.15
   ```
