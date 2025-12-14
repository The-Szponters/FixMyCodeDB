"""
Maps detailed analyzer labels to high-level category groups.
"""

from typing import Dict, Set


class LabelMapper:
    """
    Maps specific cppcheck/clang-tidy issue IDs to high-level categories
    matching the LabelsGroup schema.
    """

    # Memory-related errors
    MEMORY_ERRORS: Set[str] = {
        # Cppcheck
        "memleak", "memleakOnRealloc", "resourceLeak",
        "doubleFree", "mismatchAllocDealloc",
        "nullPointer", "nullPointerRedundantCheck", "nullPointerArithmetic",
        "uninitvar", "uninitdata", "uninitStructMember",
        "useAfterFree", "deallocret",
        # Clang
        "clang-analyzer-core.NullDereference",
        "clang-analyzer-unix.Malloc",
        "clang-analyzer-cplusplus.NewDelete",
        "clang-analyzer-cplusplus.NewDeleteLeaks",
        "bugprone-use-after-move",
    }

    # Undefined behavior issues
    UNDEFINED_BEHAVIOR: Set[str] = {
        # Cppcheck
        "arrayIndexOutOfBounds", "arrayIndexOutOfBoundsCond",
        "bufferAccessOutOfBounds", "outOfBounds",
        "shiftTooManyBits", "shiftTooManyBitsSigned",
        "integerOverflow", "signConversion",
        "invalidPointerCast", "CastIntegerToAddressAtReturn",
        "uninitStructMember", "uninitdata",
        # Clang
        "clang-analyzer-core.UndefinedBinaryOperatorResult",
        "clang-analyzer-core.uninitialized",
        "bugprone-undefined-memory-manipulation",
        "cppcoreguidelines-pro-type-reinterpret-cast",
    }

    # Correctness issues (logic errors)
    CORRECTNESS: Set[str] = {
        # Cppcheck
        "wrongPrintfScanfArgNum", "invalidFunctionArg", "invalidFunctionArgBool",
        "unreachableCode", "duplicateBreak",
        "wrongMathCall", "exceptThrowInDestructor",
        "assertWithSideEffect", "comparePointers",
        "moduloAlwaysTrueFalse", "incorrectLogicOperator",
        "oppositeInnerCondition", "identicalConditionAfterEarlyExit",
        "duplicateExpression", "duplicateConditionalAssign",
        # Clang
        "clang-analyzer-deadcode.DeadStores",
        "bugprone-branch-clone",
        "bugprone-infinite-loop",
        "bugprone-suspicious-semicolon",
        "misc-redundant-expression",
    }

    # Performance issues
    PERFORMANCE: Set[str] = {
        # Cppcheck
        "passedByValue", "constParameter", "constVariable",
        "postfixOperator", "useStlAlgorithm",
        "unreadVariable", "unusedFunction", "unusedStructMember",
        "redundantAssignment", "redundantCopy",
        # Clang
        "performance-unnecessary-copy-initialization",
        "performance-unnecessary-value-param",
        "performance-for-range-copy",
        "performance-inefficient-string-concatenation",
        "performance-move-const-arg",
    }

    # Style and readability issues
    STYLE: Set[str] = {
        # Cppcheck
        "variableScope", "functionStatic", "functionConst",
        "clarifyCalculation", "clarifyCondition",
        "redundantCondition", "redundantAssignment",
        "unusedLabel", "exceptDeallocThrow",
        # Clang
        "readability-identifier-naming",
        "readability-braces-around-statements",
        "readability-implicit-bool-conversion",
        "readability-redundant-declaration",
        "modernize-use-nullptr",
        "modernize-use-auto",
        "cppcoreguidelines-avoid-magic-numbers",
    }

    def map_to_groups(self, cppcheck_labels: Dict[str, int],
                      clang_labels: Dict[str, int]) -> Dict[str, bool]:
        """
        Maps specific issue labels to high-level category flags.

        Args:
            cppcheck_labels: Dict of cppcheck issue IDs and their counts
            clang_labels: Dict of clang-tidy check names and their counts

        Returns:
            Dict with boolean flags for each category group
        """
        # Collect all issue IDs (lowercase for case-insensitive matching)
        all_labels = set()
        for label in cppcheck_labels.keys():
            all_labels.add(label.lower())
        for label in clang_labels.keys():
            all_labels.add(label.lower())

        # Convert category sets to lowercase for matching
        memory_lower = {x.lower() for x in self.MEMORY_ERRORS}
        undefined_lower = {x.lower() for x in self.UNDEFINED_BEHAVIOR}
        correctness_lower = {x.lower() for x in self.CORRECTNESS}
        performance_lower = {x.lower() for x in self.PERFORMANCE}
        style_lower = {x.lower() for x in self.STYLE}

        return {
            "memory_errors": bool(all_labels & memory_lower),
            "undefined_behavior": bool(all_labels & undefined_lower),
            "correctness": bool(all_labels & correctness_lower),
            "performance": bool(all_labels & performance_lower),
            "style": bool(all_labels & style_lower),
        }
