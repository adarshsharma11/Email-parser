#!/usr/bin/env python3
"""
Test runner script for the Vacation Rental Booking Automation system.
"""
import sys
import os
import subprocess
import argparse

def run_tests(test_type="all", coverage=True, verbose=False):
    """
    Run the test suite.
    
    Args:
        test_type: Type of tests to run ('all', 'unit', 'integration')
        coverage: Whether to run with coverage
        verbose: Whether to run with verbose output
    """
    # Add the src directory to the Python path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    if test_type == "unit":
        cmd.extend(["-m", "unit"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
    
    if coverage:
        cmd.extend(["--cov=src", "--cov-report=term-missing"])
    
    if verbose:
        cmd.append("-v")
    
    # Add test directory
    cmd.append("tests/")
    
    print(f"Running tests: {' '.join(cmd)}")
    print("=" * 60)
    
    try:
        result = subprocess.run(cmd, check=True)
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        return 0
    except subprocess.CalledProcessError as e:
        print("\n" + "=" * 60)
        print(f"❌ Tests failed with exit code {e.returncode}")
        return e.returncode

def run_linting():
    """Run code linting checks."""
    print("Running code linting...")
    print("=" * 60)
    
    # Run flake8
    try:
        subprocess.run(["flake8", "src/", "tests/"], check=True)
        print("✅ Flake8 passed!")
    except subprocess.CalledProcessError:
        print("❌ Flake8 failed!")
        return 1
    
    # Run black check
    try:
        subprocess.run(["black", "--check", "src/", "tests/"], check=True)
        print("✅ Black formatting check passed!")
    except subprocess.CalledProcessError:
        print("❌ Black formatting check failed!")
        print("Run 'black src/ tests/' to fix formatting")
        return 1
    
    # Run mypy
    try:
        subprocess.run(["mypy", "src/"], check=True)
        print("✅ MyPy type checking passed!")
    except subprocess.CalledProcessError:
        print("❌ MyPy type checking failed!")
        return 1
    
    return 0

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Test runner for Vacation Rental Booking Automation")
    parser.add_argument(
        "--type", 
        choices=["all", "unit", "integration"], 
        default="all",
        help="Type of tests to run"
    )
    parser.add_argument(
        "--no-coverage", 
        action="store_true",
        help="Run tests without coverage"
    )
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true",
        help="Run with verbose output"
    )
    parser.add_argument(
        "--lint-only", 
        action="store_true",
        help="Run only linting checks"
    )
    parser.add_argument(
        "--test-only", 
        action="store_true",
        help="Run only tests (skip linting)"
    )
    
    args = parser.parse_args()
    
    if args.lint_only:
        return run_linting()
    
    if not args.test_only:
        print("Running linting checks...")
        lint_result = run_linting()
        if lint_result != 0:
            print("\nLinting failed. Fix the issues before running tests.")
            return lint_result
        print()
    
    return run_tests(
        test_type=args.type,
        coverage=not args.no_coverage,
        verbose=args.verbose
    )

if __name__ == "__main__":
    sys.exit(main())
