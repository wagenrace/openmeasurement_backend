import os
from typing import List
import regex as re
from fastapi import FastAPI, HTTPException
from py2neo import Graph

from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

url = os.environ["NEO4J_URL"]
user = os.environ["NEO4J_USER"]
pswd = os.environ["NEO4J_PSWD"]

graph = Graph(url, name="test", auth=(user, pswd))

"""
Synonyms with multiple compounds

"pubChemSynId": "69da37703943cfa2a7a50159cfb1fc95",
"name": "( inverted exclamation marka)-potassium citramalate monohydrate"

"pubChemSynId": "0f2e32e0f1a7f2cc034303e4ff2b7948",
"name": "((1-aza-2-(3-thienyl)vinyl)amino)(prop-2-enylamino)methane-1-thione"

"pubChemSynId": "23000d280089903b877dbe0f2b4ff646",
"name": "(+)-(18-crown-6)-2,3,11,12-tetracarboxamide"

"pubChemSynId": "b20b0d4197f8609dc17d1af12e1ca715",
"name": "(+)-2,3,4,4a,5,9b-hexahydro-5-(4-aminophenyl)-1h-indeno(1,2-b)pyridine"

"pubChemSynId": "1b464664b35b4cef85295082b46703b1",
"name": "(+)-2-methylamino-2-phenylpropane hydrochloride"

"""


@app.get("/symAutoComplete/")
async def read_item(chemical_name: str) -> list:

    # Find alls unicode characters (\p) classified as letters ({L})
    # in a group of at least 2 ({2,})
    # This also helps against (some) forms of cypher injects
    if not chemical_name:
        return []
    all_words = re.findall(r"[\p{L}\d]{2,}", chemical_name)

    all_fuzzy_names = "~ AND ".join(all_words) + "~"
    response = graph.run(
        f""" 
        CALL {{
            CALL db.index.fulltext.queryNodes('synonymsFullText', "{all_fuzzy_names}")
            YIELD node, score
            return node, score limit 50
        }}
        MATCH (node)-[:IS_ATTRIBUTE_OF]->(c:Compound)
        WITH DISTINCT c as c, collect({{score: score, node: node}})[0] as s
        WITH DISTINCT s as s, collect(c.pubChemCompId) as compoundId
        RETURN s.node.name as name, s.node.pubChemSynId as synonymId, compoundId limit 5
        """
    ).data()

    return response


@app.get("/getCompound/")
async def get_compound(compound_id: str) -> dict:
    response = graph.run(
        f""" 
        MATCH (c:Compound {{pubChemCompId: "{compound_id}"}})<-[:IS_ATTRIBUTE_OF]-(s:Synonym) 
        WITH c.pubChemCompId as id, collect(DISTINCT s.name) as synonyms
        RETURN id, synonyms
        """
    ).data()

    if len(response) == 0:
        raise HTTPException(status_code=404, detail="Compound could not be found")
    return response[0]


async def get_synonyms_name_from_id(synonym_id) -> str:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/rdf/synonym/MD5_{synonym_id}.json"
    response = requests.get(url).json()
    synonym = response[f"synonym/MD5_{synonym_id}"].get(
        "http://semanticscience.org/resource/has-value"
    )
    if synonym is None:
        return ""

    name = synonym[0].get("value", "").lower()
    return name


async def get_synonyms_from_rdf(compound_id: int) -> List[str]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/rdf/compound/CID{compound_id}.json"
    response = requests.get(url).json()
    synonym_prefix = "synonym/MD5_"
    synonym_ids = [
        i.replace(synonym_prefix, "")
        for i in response.keys()
        if i.startswith(synonym_prefix)
        and response[i].get("http://semanticscience.org/resource/is-attribute-of")
    ]
    return synonym_ids


@app.get("/getSynonymFromPubChem/")
async def get_synonym_from_pubchem(synonym_name: str) -> dict:
    pubChemUrl = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{synonym_name.lower()}/synonyms/JSON"

    response = requests.get(pubChemUrl).json()
    compounds = response.get("InformationList", {}).get("Information")
    if not compounds:
        raise HTTPException(
            status_code=404,
            detail="Synonym could not be found or did not had compounds",
        )
    return compounds


@app.get("/updateCompound/")
async def update_compounds(compound_id: int) -> dict:
    compound_id_str: str = f"compound:cid{compound_id}"
    response = graph.run(
        f""" 
        MERGE (c:Compound {{pubChemCompId: "{compound_id_str}"}})
        RETURN c
        """
    ).data()
    return response
