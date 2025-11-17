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

## TA-1

**Uruchomienie analizy nowego projektu**\
Po podaniu repozytorium Git, system filtruje commity i zapisuje w bazie
rekordy zawierające pary **code_buggy** i **code_fixed**

## TA-2

**Półautomatyczne etykietowanie**\
Rekordy zapisane w bazie są poprawnie poetykietowane na podstawie
analizy statycznej kodu **code_buggy**

## TA-3

**Aplikacja konsolowa i filtrowanie**\
Użytkownik jest w stanie uruchomić aplikację konsolową i za jej pomocą
wyszukać oraz wyświetlić przefiltrowane rekordy.

## TA-4

**Eksport do pliku**\
System poprawnie eksportuje dane do pliku **JSON/CSV**

## TA-5

**Ręczne dodawanie/edycja rekordów**\
Sprawdzenie poprawności dodawania oraz edycji rekordów
