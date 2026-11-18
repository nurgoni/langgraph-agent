"""Model API artifact (FR-46): referensi file yang diunggah user atau dibuat agent.

Docstring class ikut menjadi deskripsi di kontrak OpenAPI, jadi doctest ditaruh di sini.

>>> ArtifactRef(id="a1", name="sales.csv", mime_type="text/csv", size=120).size
120
"""

from pydantic import BaseModel, Field


class ArtifactRef(BaseModel):
    """Referensi satu artifact. Isi file diunduh lewat `GET /artifacts/{id}`."""

    id: str = Field(examples=["0b9e3c1e-5f7a-4c2b-9d61-3f0a2b7c8d90"])
    name: str = Field(description="Nama file yang sudah disanitasi.", examples=["sales.csv"])
    mime_type: str = Field(description="Tipe konten file.", examples=["text/csv"])
    size: int = Field(ge=0, description="Ukuran file dalam byte.", examples=[2048])


if __name__ == "__main__":
    print(ArtifactRef(id="a1", name="chart.png", mime_type="image/png", size=4096))
