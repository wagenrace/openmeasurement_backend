import hashlib
from typing import List

import requests


def synonyms_2_synonym_id(synonym_name: str) -> str:
    return hashlib.md5(synonym_name.lower().encode("utf-8")).hexdigest()


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
        {
            "id": i.replace(synonym_prefix, ""),
            "name": await get_synonyms_name_from_id(i.replace(synonym_prefix, "")),
        }
        for i in response.keys()
        if i.startswith(synonym_prefix)
        and response[i].get("http://semanticscience.org/resource/is-attribute-of")
    ]
    return synonym_ids


async def get_compound_from_synonym_name(synonym_name: str) -> List[dict]:
    pubChemUrl = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{synonym_name.lower()}/synonyms/JSON"

    response = requests.get(pubChemUrl).json()
    compounds = response.get("InformationList", {}).get("Information")
    for compound in compounds:
        rdf_synonyms = await get_synonyms_from_rdf(compound["CID"])
        rest_synonyms_names = compound.get("Synonym", [])
        rest_synonyms = [
            {"id": synonyms_2_synonym_id(i), "name": i.lower()}
            for i in rest_synonyms_names
        ]
        compound["Synonym"] = rdf_synonyms + rest_synonyms
    return compounds
