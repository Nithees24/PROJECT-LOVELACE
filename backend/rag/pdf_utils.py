from langchain_community.document_loaders import (
    PyMuPDFLoader,
    Docx2txtLoader,
    TextLoader,
    UnstructuredExcelLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List
import os

def extract_text_from_file(file_path: str) -> str:
    """Extracts text from various file types (.pdf, .docx, .txt, .xlsx) using LangChain loaders."""
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if ext == ".pdf":
            loader = PyMuPDFLoader(file_path)
        elif ext == ".docx":
            loader = Docx2txtLoader(file_path)
        elif ext == ".txt":
            loader = TextLoader(file_path, encoding="utf-8")
        elif ext in [".xlsx", ".xls"]:
            # Note: UnstructuredExcelLoader requires 'unstructured' and 'openpyxl'
            loader = UnstructuredExcelLoader(file_path, mode="elements")
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
            
        docs = loader.load()
        return "\n".join([doc.page_content for doc in docs])
    except Exception as e:
        print(f"Error loading document {file_path}: {e}")
        raise e

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Splits text into chunks using LangChain's RecursiveCharacterTextSplitter."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=len,
        is_separator_regex=False,
    )
    return text_splitter.split_text(text)
