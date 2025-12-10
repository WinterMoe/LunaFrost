                      

import sys
import os

                              
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

                                                             
from dotenv import load_dotenv
load_dotenv()

from database.database import db_session_scope
from database.db_models import User

def show_usage():
    print("Usage: python scripts/make_admin.py <username> [--grant|--revoke]")
    print()
    print("Examples:")
    print("  python scripts/make_admin.py johndoe --grant    # Grant admin")
    print("  python scripts/make_admin.py johndoe --revoke   # Revoke admin")
    print("  python scripts/make_admin.py johndoe            # Toggle admin")
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        show_usage()
    
    username = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else 'toggle'
    
    if action not in ['--grant', '--revoke', 'toggle']:
        print(f"❌ Invalid action: {action}")
        show_usage()
    
    with db_session_scope() as session:
        user = session.query(User).filter(User.username == username).first()
        
        if not user:
            print(f"❌ User not found: {username}")
            print("\n📋 Available users:")
            users = session.query(User).all()
            for u in users:
                admin_badge = "👑 ADMIN" if u.is_admin else ""
                print(f"   - {u.username} {admin_badge}")
            sys.exit(1)
        
                        
        if action == '--grant':
            if user.is_admin:
                print(f"ℹ️  {username} is already an admin")
            else:
                user.is_admin = True
                session.commit()
                print(f"✅ {username} is now an admin 👑")
        
        elif action == '--revoke':
            if not user.is_admin:
                print(f"ℹ️  {username} is not an admin")
            else:
                user.is_admin = False
                session.commit()
                print(f"✅ Admin privileges revoked from {username}")
        
        else:          
            user.is_admin = not user.is_admin
            session.commit()
            status = "an admin 👑" if user.is_admin else "not an admin"
            print(f"✅ {username} is now {status}")

if __name__ == '__main__':
    main()