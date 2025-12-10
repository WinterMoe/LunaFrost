                      

import sys
import os

                              
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

                                                             
from dotenv import load_dotenv
load_dotenv()

from database.database import db_session_scope
from database.db_models import User

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_admin.py <username>")
        sys.exit(1)
    
    username = sys.argv[1]
    
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
        
        if user.is_admin:
            print(f"✅ {username} IS an admin 👑")
        else:
            print(f"❌ {username} is NOT an admin")
            print(f"\nTo make this user an admin, run:")
            print(f"  python scripts/make_admin.py {username} --grant")

if __name__ == '__main__':
    main()
