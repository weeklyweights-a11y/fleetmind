class FleetMindError(Exception):
    def __init__(self, message: str, error_code: str = "FLEETMIND_ERROR", details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class DatabaseError(FleetMindError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, error_code="DATABASE_ERROR", details=details)


class DocumentNotFoundError(FleetMindError):
    def __init__(self, document_id: str):
        super().__init__(
            f"Document {document_id} not found",
            error_code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )


class DocumentProcessingError(FleetMindError):
    def __init__(self, message: str, error_code: str = "DOCUMENT_PROCESSING_ERROR", details: dict | None = None):
        super().__init__(message, error_code=error_code, details=details)


class ExtractionValidationError(FleetMindError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, error_code="EXTRACTION_VALIDATION_ERROR", details=details)


class TruckNotFoundError(FleetMindError):
    def __init__(self, truck_id: str):
        super().__init__(
            f"Truck {truck_id} not found",
            error_code="TRUCK_NOT_FOUND",
            details={"truck_id": truck_id},
        )


class DriverNotFoundError(FleetMindError):
    def __init__(self, driver_id: str):
        super().__init__(
            f"Driver {driver_id} not found",
            error_code="DRIVER_NOT_FOUND",
            details={"driver_id": driver_id},
        )


class VendorNotFoundError(FleetMindError):
    def __init__(self, vendor_id: str):
        super().__init__(
            f"Vendor {vendor_id} not found",
            error_code="VENDOR_NOT_FOUND",
            details={"vendor_id": vendor_id},
        )


def is_not_found_error(exc: FleetMindError) -> bool:
    return exc.error_code.endswith("_NOT_FOUND")
