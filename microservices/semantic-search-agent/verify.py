#!/usr/bin/env python3
"""
Project verification script.
Checks that all required files exist and have correct structure.
"""

import sys
from pathlib import Path


def check_file_exists(path: Path, description: str) -> bool:
    """Check if file exists."""
    if path.exists():
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"❌ {description} missing: {path}")
        return False


def check_directory_exists(path: Path, description: str) -> bool:
    """Check if directory exists."""
    if path.exists() and path.is_dir():
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"❌ {description} missing: {path}")
        return False


def main():
    """Run verification checks."""
    root = Path(__file__).parent
    all_checks_passed = True
    
    print("🔍 Semantic Comparison Service - Project Verification")
    print("=" * 60)
    
    # Check core directories
    print("\n📁 Checking Directories:")
    directories = [
        (root / "app", "Application code"),
        (root / "app" / "api", "API layer"),
        (root / "app" / "core", "Core infrastructure"),
        (root / "app" / "services", "Services layer"),
        (root / "app" / "services" / "matchers", "Matcher strategies"),
        (root / "app" / "services" / "vlm", "VLM backends"),
        (root / "app" / "utils", "Utilities"),
        (root / "tests", "Test suite"),
        (root / "config", "Configuration"),
        (root / "docker", "Docker files"),
    ]
    
    for path, desc in directories:
        if not check_directory_exists(path, desc):
            all_checks_passed = False
    
    # Check critical files
    print("\n📄 Checking Core Files:")
    core_files = [
        (root / "app" / "main.py", "FastAPI application"),
        (root / "app" / "api" / "routes.py", "API routes"),
        (root / "app" / "api" / "models.py", "API models"),
        (root / "app" / "core" / "config.py", "Configuration"),
        (root / "app" / "services" / "comparison_engine.py", "Comparison engine"),
        (root / "requirements.txt", "Python dependencies"),
        (root / "docker" / "Dockerfile", "Docker image"),
        (root / "docker" / "docker-compose.yml", "Docker compose"),
    ]
    
    for path, desc in core_files:
        if not check_file_exists(path, desc):
            all_checks_passed = False
    
    # Check matcher implementations
    print("\n🎯 Checking Matcher Implementations:")
    matchers = [
        (root / "app" / "services" / "matchers" / "base.py", "Base matcher"),
        (root / "app" / "services" / "matchers" / "exact.py", "Exact matcher"),
        (root / "app" / "services" / "matchers" / "semantic.py", "Semantic matcher"),
        (root / "app" / "services" / "matchers" / "hybrid.py", "Hybrid matcher"),
    ]
    
    for path, desc in matchers:
        if not check_file_exists(path, desc):
            all_checks_passed = False
    
    # Check VLM backends
    print("\n🤖 Checking VLM Backends:")
    backends = [
        (root / "app" / "services" / "vlm" / "base.py", "Base backend"),
        (root / "app" / "services" / "vlm" / "ovms.py", "OVMS backend"),
        (root / "app" / "services" / "vlm" / "openvino_local.py", "OpenVINO local"),
        (root / "app" / "services" / "vlm" / "openai.py", "OpenAI backend"),
    ]
    
    for path, desc in backends:
        if not check_file_exists(path, desc):
            all_checks_passed = False
    
    # Check test files
    print("\n🧪 Checking Tests:")
    tests = [
        (root / "tests" / "conftest.py", "Test configuration"),
        (root / "tests" / "test_api.py", "API tests"),
        (root / "tests" / "test_matchers.py", "Matcher tests"),
        (root / "tests" / "test_comparison_engine.py", "Engine tests"),
        (root / "tests" / "test_utils.py", "Utility tests"),
    ]
    
    for path, desc in tests:
        if not check_file_exists(path, desc):
            all_checks_passed = False
    
    # Check configuration files
    print("\n⚙️  Checking Configuration:")
    configs = [
        (root / "config" / "service_config.yaml", "Service config"),
        (root / "config" / "orders.json", "Orders database"),
        (root / "config" / "inventory.json", "Inventory list"),
        (root / ".env.example", "Environment template"),
    ]
    
    for path, desc in configs:
        if not check_file_exists(path, desc):
            all_checks_passed = False
    
    # Check documentation
    print("\n📚 Checking Documentation:")
    docs = [
        (root / "README.md", "Main README"),
        (root / "DEPLOYMENT.md", "Deployment guide"),
        (root / "IMPLEMENTATION_PLAN.md", "Implementation plan"),
        (root / "PROJECT_SUMMARY.md", "Project summary"),
        (root / "QUICK_REFERENCE.md", "Quick reference"),
    ]
    
    for path, desc in docs:
        if not check_file_exists(path, desc):
            all_checks_passed = False
    
    # Check build files
    print("\n🔧 Checking Build Files:")
    build_files = [
        (root / "Makefile", "Build automation"),
        (root / "pyproject.toml", "Python project config"),
        (root / "quick-start.sh", "Quick start script"),
        (root / ".gitignore", "Git ignore rules"),
    ]
    
    for path, desc in build_files:
        if not check_file_exists(path, desc):
            all_checks_passed = False
    
    # Count lines of code
    print("\n📊 Code Statistics:")
    try:
        import subprocess
        
        app_loc = subprocess.run(
            ["find", "app", "-name", "*.py", "-exec", "wc", "-l", "{}", "+"],
            cwd=root,
            capture_output=True,
            text=True
        )
        if app_loc.returncode == 0:
            lines = app_loc.stdout.strip().split("\n")[-1]
            print(f"   Application Code: {lines.split()[0]} lines")
        
        test_loc = subprocess.run(
            ["find", "tests", "-name", "*.py", "-exec", "wc", "-l", "{}", "+"],
            cwd=root,
            capture_output=True,
            text=True
        )
        if test_loc.returncode == 0:
            lines = test_loc.stdout.strip().split("\n")[-1]
            print(f"   Test Code: {lines.split()[0]} lines")
    except Exception as e:
        print(f"   ⚠️  Could not count lines: {e}")
    
    # Final result
    print("\n" + "=" * 60)
    if all_checks_passed:
        print("✅ All checks passed! Project structure is complete.")
        print("\n🚀 Next steps:")
        print("   1. Review README.md for quick start")
        print("   2. Run: make install")
        print("   3. Run: make test")
        print("   4. Run: make docker-up")
        return 0
    else:
        print("❌ Some checks failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
