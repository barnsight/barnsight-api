import asyncio

import cloudinary
import cloudinary.api
import cloudinary.uploader
from core.config import settings
from core.logger import logger
from fastapi import HTTPException, UploadFile, status


def init_cloudinary():
  """Initialize Cloudinary configuration."""
  if (
    settings.CLOUDINARY_CLOUD_NAME
    and settings.CLOUDINARY_API_KEY
    and settings.CLOUDINARY_API_SECRET
  ):
    cloudinary.config(
      cloud_name=settings.CLOUDINARY_CLOUD_NAME,
      api_key=settings.CLOUDINARY_API_KEY,
      api_secret=settings.CLOUDINARY_API_SECRET,
      secure=True,
    )

    # Increase urllib3 connection pool size for concurrent uploads
    from cloudinary.utils import get_http_connector

    options = cloudinary.CERT_KWARGS.copy()
    options["maxsize"] = 100
    cloudinary.uploader._http = get_http_connector(cloudinary.config(), options)

    logger.info("Cloudinary configured successfully.")
  else:
    logger.warning("Cloudinary credentials not found. Image uploads may fail.")


async def upload_image(file: UploadFile, folder: str = "barnsight") -> str:
  """
  Upload an image to Cloudinary and return the secure URL.

  Args:
      file (UploadFile): The file to upload.
      folder (str, optional): The folder in Cloudinary. Defaults to "barnsight".

  Returns:
      str: The secure URL of the uploaded image.

  Raises:
      HTTPException: If the upload fails.
  """
  try:
    # Read file content
    content = await file.read()

    # Cloudinary upload is blocking, so we run it in a thread
    result = await asyncio.to_thread(
      cloudinary.uploader.upload, content, folder=folder, resource_type="image"
    )

    return result.get("secure_url")
  except Exception as e:
    logger.error(f"Failed to upload image to Cloudinary: {str(e)}")
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="Failed to upload image to Cloudinary",
    )


async def upload_base64_image(base64_string: str, folder: str = "barnsight/events") -> str:
  """
  Upload a base64 encoded image to Cloudinary and return the secure URL.

  Args:
      base64_string (str): The base64 string of the image.
      folder (str, optional): The folder in Cloudinary.

  Returns:
      str: The secure URL of the uploaded image.
  """
  try:
    # Ensure it has the data URI scheme if not present
    if not base64_string.startswith("data:image"):
      # Assume JPEG if not specified, Cloudinary often auto-detects
      base64_data = f"data:image/jpeg;base64,{base64_string}"
    else:
      base64_data = base64_string

    result = await asyncio.to_thread(
      cloudinary.uploader.upload, base64_data, folder=folder, resource_type="image"
    )

    return result.get("secure_url")
  except Exception as e:
    logger.error(f"Failed to upload base64 image to Cloudinary: {str(e)}")
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="Failed to upload image to Cloudinary",
    )


async def delete_image(public_id: str) -> bool:
  """
  Delete an image from Cloudinary by its public ID.

  Args:
      public_id (str): The public ID of the image.

  Returns:
      bool: True if deleted successfully.
  """
  try:
    result = await asyncio.to_thread(cloudinary.uploader.destroy, public_id)
    return result.get("result") == "ok"
  except Exception as e:
    logger.error(f"Failed to delete image from Cloudinary: {str(e)}")
    return False
