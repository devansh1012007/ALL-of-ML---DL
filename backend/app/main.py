from fastapi import FastAPI, Depends, HTTPException, status, Body
import logging 
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .models import User
from .auth import ALGORITHM, SECRET_KEY, verify_pass, create_token, hash_pass
from pydantic import BaseModel
from typing import Optional


app = FastAPI(title="PrimeTrade Secure Notes API")

# log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"), # Saves logs to this file
        logging.StreamHandler()         # Prints logs to the console
    ]
)
logger = logging.getLogger("PrimeTradeAPI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class UserCreate(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise HTTPException(status_code=401)
    except JWTError: raise HTTPException(status_code=401)
    
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None: raise HTTPException(status_code=401)
    return user

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

# auth
@app.post("/api/v1/register")
async def register(user: UserCreate, db=Depends(get_db)):
    logger.info(f"Registration attempt for new user: '{user.username}'")
    
    safe_password = user.password[:72] 
    hashed = hash_pass(safe_password)
    
    new_user = User(
        username=user.username, 
        hashed_password=hashed, 
        role=user.role
    )
    db.add(new_user)
    await db.commit()
    
    logger.info(f"Success: User '{user.username}' registered with role '{user.role}'.")
    return {"message": "User registered successfully"}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    logger.info(f"Login attempt for user: '{form_data.username}'")
    
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()
    
    if not user or not verify_pass(form_data.password, user.hashed_password):
        logger.warning(f"Failed login: Incorrect credentials for '{form_data.username}'")
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    logger.info(f"Success: User '{user.username}' logged in successfully.")
    access_token = create_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/v1/admin/all-users")
async def get_all_users(admin_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

# now i will add simple interface endpoints to make diffent ML and DL models