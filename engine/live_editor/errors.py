class LiveEditError(RuntimeError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details

    def as_dict(self):
        return {"code": self.code, "message": str(self), "details": self.details}


def require(condition, code, message, details=None):
    if not condition:
        raise LiveEditError(code, message, details)
