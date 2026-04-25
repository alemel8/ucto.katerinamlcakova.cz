from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client
from ..schemas import ClientCreate, ClientResponse
from .invoices import get_user_flexible

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=List[ClientResponse])
def list_clients(
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    return db.query(Client).order_by(Client.name).all()


@router.post("", response_model=ClientResponse, status_code=201)
def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    existing = db.query(Client).filter(Client.ico == data.ico).first()
    if existing:
        raise HTTPException(status_code=400, detail="Klient s tímto IČ již existuje")
    client = Client(ico=data.ico, name=data.name)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.put("/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: int,
    data: ClientCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Klient nenalezen")
    # Check ICO uniqueness if changed
    if data.ico != client.ico:
        existing = db.query(Client).filter(Client.ico == data.ico).first()
        if existing:
            raise HTTPException(status_code=400, detail="Klient s tímto IČ již existuje")
    client.ico = data.ico
    client.name = data.name
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Klient nenalezen")
    db.delete(client)
    db.commit()
