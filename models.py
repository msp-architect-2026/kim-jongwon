from datetime import datetime

from extensions import db


class Strategy(db.Model):
    __tablename__ = "strategies"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.String(20), nullable=False)
    params = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "params": self.params,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
