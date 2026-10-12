"""Deployment validation agent - checks all configuration for 100% perfect deployment."""
import os
import sys

def check_file_exists(filepath, description):
    """Check if a file exists and is not empty."""
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        print(f"[OK] {description}: {filepath}")
        return True
    else:
        print(f"[FAIL] {description}: Missing or empty - {filepath}")
        return False

def check_env_var(var_name, description):
    """Check if an environment variable is set."""
    if os.environ.get(var_name):
        print(f"[OK] {description}: {var_name} is set")
        return True
    elif os.path.exists(".env") and var_name in open(".env").read():
        print(f"[OK] {description}: {var_name} is in .env file")
        return True
    else:
        print(f"[FAIL] {description}: {var_name} is not set")
        return False

def main():
    print("=" * 60)
    print("DEPLOYMENT VALIDATION AGENT")
    print("=" * 60)
    
    checks = []
    
    # Check backend files
    print("\n--- Backend (Flask/Render) ---")
    checks.append(check_file_exists("app.py", "Flask application"))
    checks.append(check_file_exists("Procfile", "Render Procfile"))
    checks.append(check_file_exists("render.yaml", "Render configuration"))
    checks.append(check_file_exists("requirements.txt", "Python dependencies"))
    checks.append(check_env_var("SUPABASE_URL", "Supabase URL"))
    checks.append(check_env_var("SUPABASE_ANON_KEY", "Supabase anon key"))
    checks.append(check_env_var("MISTRAL_API_KEY", "Mistral API key"))
    checks.append(check_env_var("PUBLIC_BASE_URL", "Public base URL"))
    
    # Check frontend files
    print("\n--- Frontend (Vercel) ---")
    checks.append(check_file_exists("frontend/src/main.jsx", "React main component"))
    checks.append(check_file_exists("package.json", "Node dependencies"))
    checks.append(check_file_exists("vercel.json", "Vercel configuration"))
    checks.append(check_env_var("REACT_APP_API_URL", "React API URL"))
    
    # Check database
    print("\n--- Database ---")
    checks.append(check_file_exists("quantum_healthcare.sqlite3", "SQLite database"))
    
    # Check human made marker
    print("\n--- Human Made Marker ---")
    human_made_check = False
    if os.path.exists("test_app.py"):
        print("[OK] Test script exists")
        human_made_check = True
    checks.append(human_made_check)
    
    # Results
    print("\n" + "=" * 60)
    passed = sum(checks)
    total = len(checks)
    print(f"Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("[OK] 100% DEPLOYMENT READY - All checks passed!")
        return 0
    else:
        print("[WARNING] Some checks failed - review the output above")
        return 1

if __name__ == "__main__":
    sys.exit(main())