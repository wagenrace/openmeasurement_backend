import os

import regex as re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from py2neo import Graph
from .types import Synonym

from .pubchem_connections import get_compound_from_synonym_name
from .encode_for_neo4j import encode2neo4j

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default are for local testing
url = os.environ.get("NEO4J_URL", "bolt://localhost:7687")
user = os.environ.get("NEO4J_USER", "neo4j")
pswd = os.environ.get("NEO4J_PSWD", "password")

graph = Graph(url, auth=(user, pswd))


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
        MATCH (c:Compound {{pubChemCompId: "{compound_id}"}})
        OPTIONAL MATCH (c)<-[:IS_ATTRIBUTE_OF]-(s:Synonym) 
        WITH c.pubChemCompId as id, collect(DISTINCT s.name) as synonyms
        RETURN id, synonyms
        """
    ).data()

    if len(response) == 0:
        raise HTTPException(status_code=404, detail="Compound could not be found")
    return response[0]


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


@app.get("/updatePubchemSynonymsByName/")
async def update_by_synonym_name(synonym_name: str):
    all_compounds = await get_compound_from_synonym_name(synonym_name)
    print(f"found {len(all_compounds)} compounds for synonym {synonym_name}")
    for compound in all_compounds:
        update_compound(compound["CID"], compound["Synonym"])
    return all_compounds


def update_compound(compound_id: int, synonyms: list[Synonym]):
    compound_id_str = f"compound:cid{compound_id}"

    # Delete all synonyms NOT in the given list
    # But that do exist in the current database
    graph.run(
        f""" 
        MATCH (c:Compound {{pubChemCompId: "{compound_id_str}"}})<-[r:IS_ATTRIBUTE_OF]-(s:Synonym) 
        WHERE NOT s.pubChemSynId IN {[i.id for i in synonyms]}
        DELETE r
        """
    )

    # Create all the new synonyms and connections to the compound
    query = f""" 
        MERGE (c:Compound {{pubChemCompId: "{compound_id_str}"}})
        """
    for idx, s in enumerate(synonyms):
        query += f"""MERGE (s{idx}:Synonym {{pubChemSynId: "{s.id}", name: "{encode2neo4j(s.name)}"}})
        MERGE (c)<-[:IS_ATTRIBUTE_OF]-(s{idx})
        """
    print(query)
    graph.run(query)
