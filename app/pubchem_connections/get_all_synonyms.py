import hashlib

import requests

from ..types import Synonym


def synonyms_2_synonym_id(synonym_name: str) -> str:
    """Turn synonym name into md5 hash encoding used by pubChem
    md5 hashing of lowercase name

    Args:
        synonym_name (str): Name of synonym

    Returns:
        str: generated id of synonym
    """
    return hashlib.md5(synonym_name.lower().encode("utf-8")).hexdigest()


async def get_synonyms_name_from_id(synonym_id: str) -> str:
    """Uses the rdf rest api to get the synonym name based on its idea
    Generated ID might not be found

    Args:
        synonym_id (str): md5 encoding of the name

    Returns:
        str: name of synonym
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/rdf/synonym/MD5_{synonym_id}.json"
    response = requests.get(url)
    if response.status_code >= 300 or response.status_code < 200:
        return ""
    response_json = response.json()
    synonym = response_json[f"synonym/MD5_{synonym_id}"].get(
        "http://semanticscience.org/resource/has-value"
    )
    if synonym is None:
        return ""

    name = synonym[0].get("value", "").lower()
    return name


async def get_synonyms_ids_from_rdf(compound_id: int) -> list[str]:
    """Get all synonyms of a compound using the RDF rest api

    Args:
        compound_id (int): compound id

    Returns:
        List[str]: list of ids
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/rdf/compound/CID{compound_id}.json"
    response = requests.get(url)
    if response.status_code >= 300 or response.status_code < 200:
        return []

    response_json = response.json()
    synonym_prefix = "synonym/MD5_"
    synonym_ids = [
        Synonym(
            id=i.replace(synonym_prefix, ""),
            name=await get_synonyms_name_from_id(i.replace(synonym_prefix, "")),
        )
        for i in response_json.keys()
        if i.startswith(synonym_prefix)
        and response_json[i].get("http://semanticscience.org/resource/is-attribute-of")
    ]
    return synonym_ids


async def get_compound_from_synonym_name(synonym_name: str) -> list[dict]:
    """get compounds of a synonym by its name
    used the PUG API (not RDF)

    Args:
        synonym_name (str): name of synonym

    Returns:
        List[dict]: compounds
    """
    pubChemUrl = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{synonym_name.lower()}/synonyms/JSON"

    response = requests.get(pubChemUrl).json()
    compounds = response.get("InformationList", {}).get("Information", [])
    for compound in compounds:
        # Get the synonyms of RDF
        rdf_synonyms = await get_synonyms_ids_from_rdf(compound["CID"])

        # Given every PUG synonym a constructed ID
        pug_synonyms_names = compound.get("Synonym", [])
        pug_synonyms = [
            Synonym(name=i.lower(), id=synonyms_2_synonym_id(i))
            for i in pug_synonyms_names
        ]

        # Remove synonyms with duplicate id
        all_synonyms = []
        for i in rdf_synonyms + pug_synonyms:
            if i.id in [i.id for i in all_synonyms]:
                continue
            all_synonyms.append(i)
        compound["Synonym"] = all_synonyms
    return compounds
