---
license: other
license_name: common-crawl
license_link: LICENSE
task_categories:
- text-generation
language:
- en
pretty_name: Clinical Guidelines
size_categories:
- 10K<n<100K
configs:
- config_name: default
  data_files:
  - split: train
    path: open_guidelines.jsonl
tags:
- medical
- health
dataset_info:
  features:
  - name: id
    dtype: string
  - name: source
    dtype: string
  - name: title
    dtype: string
  - name: clean_text
    dtype: string
  - name: raw_text
    dtype: string
  - name: url
    dtype: string
  - name: overview
    dtype: string
---

### 🎉 **NEW DROP** 🎉 PubMed Guidelines

We just added 1627 clinical guidelines found in PubMed and PubMed Central to the dataset on December 23rd, 2023. Merry Christmas!

# Clinical Guidelines

The Clinical Guidelines corpus is a new dataset of 47K clinical practice guidelines from 17 high-quality online medical sources. This dataset serves as a crucial component of the original training corpus of the [Meditron](https://huggingface.co/epfl-llm/meditron-70b) Large Language Model (LLM). We publicly release a subset of 37K articles from our Guidelines corpus, extracted from 9 of 17 sources that allow content redistribution, namely CCO, CDC, CMA, ICRC, NICE, PubMed, SPOR, WHO and WikiDoc. 

You can scrape and clean all 17 guideline sources using our code in [epfLLM/meditron](https://github.com/epfLLM/meditron). 

<img width=75% src="sources.png" alt="Sources of Clinical Practice Guidelines" title="CPG sources">


## Dataset Details

<!-- Provide a longer summary of what this dataset is. -->

- **Curated by:** [EPFL LLM Team](https://huggingface.co/epfl-llm)
- **Language(s):** English only
- **License:** [Common Crawl Foundation Terms of Use](https://commoncrawl.org/terms-of-use)
- **Repository:** [epfLLM/meditron](https://github.com/epfLLM/meditron)
- **Paper:** *[MediTron-70B: Scaling Medical Pretraining for Large Language Models](https://arxiv.org/abs/2311.16079)*
- **Knowledge Cutoff**: August 2023

## Dataset Creation

### Curation Rationale

<!-- Motivation for the creation of this dataset. -->

The dataset was curated to provide a high-quality collection of clinical practice guidelines (CPGs) for the medical training of LLMs. Our Clinical Guidelines corpus comprises 48,096 articles from 17 globally recognized sources for clinician and patient-directed guidance across high and low-resource settings, multiple medical domains (internal medicine, pediatrics, oncology, infectious disease, etc.) and multiple geographical locations. 

### Source Data

<!-- This section describes the source data (e.g. news text and headlines, social media posts, translated sentences, ...). -->

Clinical practice guidelines are rigorously researched frameworks designed to guide healthcare practitioners and patients in making evidence-based decisions regarding diagnosis, treatment, and management. 
They are compiled through a systematic process of collaborative consensus between experts to establish recommendations from the latest evidence on best practices that would maximize benefit in light of practical concerns such as available resources and context. As a super-synthesis of meta-analyses, they sit atop the *evidence pyramid* and form the basis of actionable evidence-based practice. 

Clinical guidelines differ based on several factors:

- **Organizational level**: CPGs are produced at various organizational granularities, ranging from global to hospital-level initiatives directed by international professional medical associations to informal consortia, regional or national governmental bodies to individual NGOs and hospitals. 
- **Geographic scope**: The geographic scope ranges from global (WHO) to national (CDC, NICE) and regional (Ontario, Melbourne) to institutional (ICRC, Mayo Clinic). This corpus is biased towards English-speaking regions due to its exclusive focus on English content. 
- **Resource level**: The corpus also represents health care concerns from high- (Ontario, Melbourne), low- (WHO), and volatile- (ICRC) resource settings.
- **Audience level**: Guidelines also contains a range of technical and conversational vocabulary with target audiences of clinicians or patients (or both), and is sometimes highly specialized within a theme (cancer, pediatrics, infectious disease).
- **Peer-review**: The peer review processes also ranged from UN bodies (WHO), institutional review boards (ICRC), professional associations (AAFP) to publicly crowdsourced knowledge bases (WikiDoc). 
- **Document size**: Article length varies widely from very short statements to 100+ page guides.

#### Who are the source data producers?

<!-- This section describes the people or systems who originally created the data. It should also include self-reported demographic or identity information for the source data creators if this information is available. -->

The dataset is sourced from 17 globally recognized medical entities, covering a wide range of healthcare contexts and audiences. 

We employed pragmatic selection criteria over medical sources, seeking CPGs that were: 

- (1) open-access
- (2) systematically formatted with homogenous textual structure (i.e., in a format in which automated processes could be deployed without excessive risk of misaligning textual sequences)
- (3) in the language predominantly represented by the pre-training corpus of Llama (i.e., English)
- (4) covering a breadth of medical sub-domains, audiences (clinician, nurse, patient), and resource settings (high, low, and humanitarian response settings)

| Source | Full Name | Tag | Guidelines | Words | Audience | Country | Released |
|-|-|-|-|-|-|-|-|
| **[AAFP](https://www.aafp.org)** | American Academy of Family Physicians | `aafp` | 50 | 9.4K | Doctor | USA | No |
| **[CCO](https://www.cancercareontario.ca/en/guidelines-advice)** | Cancer Care Ontario | `cco` | 87 | 199K | Doctor | Canada | **Yes** |
| **[CDC](https://www.cdc.gov/)** | Center for Disease Control and Prevention | `cdc` | 621 | 6.7M | Doctor | USA | **Yes** |
| **[CMA](https://joulecma.ca/)** | Canadian Medical Association | `cma` | 431 | 1.7M | Doctor | Canada | **Yes** |
| **[CPS](https://cps.ca)** | Canadian Paediatric Society | `cps` | 54 | 133K | Doctor | Canada | No |
| **[drugs.com](https://www.drugs.com/)** | Drugs.com | `drugs` | 6548 | 4.1M | Both | International | No |
| **[GuidelineCentral](https://www.guidelinecentral.com/)** | GuidelineCentral | `gc` | 1029 | 1M | Doctor | Mix | No |
| **[ICRC](http://icrc.org/)** | International Committee of the Red Cross | `icrc` | 49 | 1.2M | Doctor | International | **Yes** |
| **[IDSA](https://www.idsociety.org/)** | Infectious Diseases Society of America | `idsa` | 47 | 646K | Doctor | USA | No |
| **[MAGIC](https://magicevidence.org/)** | Making GRADE The Irresistible Choice | `magic` | 52 | 415K | Doctor | Mix | No |
| **[MayoClinic](https://www.mayoclinic.org/)** | MayoClinic | `mayo` | 1100 | 2.2M | Patient | USA | No |
| **[NICE](https://www.nice.org.uk/guidance)** | National Institute for Health and Care Excellence | `nice` | 1656 | 8.1M | Doctor | UK | **Yes** |
| **[PubMed](https://pubmed.ncbi.nlm.nih.gov)** | PubMed | `pubmed` | 1627 | 10.8M | Doctor | Mix | **Yes** |
| **[RCH](https://www.rch.org.au/clinicalguide/about_rch_cpgs/welcome_to_the_clinical_practice_guidelines/)** | Royal Children's Hospital Melbourne | `rch` | 384 | 410K | Doctor | Australia | No |
| **[SPOR](https://sporevidencealliance.ca/key-activities/cpg-asset-map/cpg-database/)** | Strategy for Patient-Oriented Research | `spor` | 217 | 1.1M | Doctor | Canada | **Yes** |
| **[WHO](https://www.who.int/publications/who-guidelines)** | World Health Organization | `who` | 223 | 3.1M | Both | International | **Yes** |
| **[WikiDoc](https://www.wikidoc.org/)** | WikiDoc | `wikidoc` | 33058 | 34M | Both | International | **Yes** |


#### Data Collection and Processing

<!-- This section describes the data collection and processing process such as data selection criteria, filtering and normalization methods, tools and libraries used, etc. -->

PDF documents were converted to text using [GROBID](https://github.com/kermitt2/grobid). 
After extracting the raw text from each source, we cleaned data with an ad-hoc process to exclude irrelevant or repetitive content that did not contribute to the textual content, such as URLs, references, figures, table delimiters, and ill-formatted characters. 
This filtering procedure was performed differently for each source using a sample of 50 articles. Please note that this procedure is not perfect, as it may have removed useful information or kept superfluous content. We provide the `raw_text` for each article if you would like to perform your own cleaning step. 
Additionally, the text was standardized to a unified format with hierarchical section headers indicated by `'#'`, homogenous spacing `'\n\n'` separating paragraphs, and normalized lists formatted with `'- '` bullet points. 
Finally, all samples were deduplicated using title matching, and articles that were too short or not English were filtered out. 

#### Personal and Sensitive Information

<!-- State whether the dataset contains data that might be considered personal, sensitive, or private (e.g., data that reveals addresses, uniquely identifiable names or aliases, racial or ethnic origins, sexual orientations, religious beliefs, political opinions, financial or health data, etc.). If efforts were made to anonymize the data, describe the anonymization process. -->

As the articles are publicly accessible, no personal or sensitive information is included.

## Dataset Structure

<!-- This section provides a description of the dataset fields, and additional information about the dataset structure such as criteria used to create the splits, relationships between data points, etc. -->

Each row of the dataset represents one clinical practice guideline article, and consists of the following dataset fields (all strings): 


| Field       | Description                               | Sources with field           |
|-------------|-------------------------------------------|------------------------------|
| `id`        | Unique identifier for each article        | All                          |
| `source`    | Source tag (`cco`, `cdc`, `cma`, `icrc`, `nice`, `spor`, `who` or `wikidoc`)| All  |
| `title`     | Title of the article                       | CMA, NICE & WikiDoc      |
| `url`       | URL of the article                         | NICE, WikiDoc & PubMed |
| `raw_text`  | Unprocessed scraped article text          | All    |
| `clean_text`| Cleaned and formatted article text        | All                          |
| `overview`  | Short summary or abstract of the article               | NICE & Pubmed                     |


## Uses

<!-- Address questions around how the dataset is intended to be used. -->

The dataset is intended for use in tasks related to text generation, specifically in the context of clinical practice guidelines. It can be employed for training language models and other natural language processing applications within the healthcare domain.

### Out-of-Scope Use

<!-- This section addresses misuse, malicious use, and uses that the dataset will not work well for. -->

- **Redistribution**: Please always check redistribution licenses before using the content as these may also evolve over time. To the best of our knowledge, we are following the redistribution licensing of each source and we invite users to inform us if that is not the case.
- **Malicious use**: We do not support any use of this corpus that may be harmful. Creating tools that provide clinical advice is commendable, but extremely dangerous if not done with the appropriate care. Such tools need to be validated for safety and utility by medical professionals in randomized controlled trials. i.e. please do not create cowboy health apps that fool vulnerable users into thinking they are receiving validated advice.


## Bias, Risks, and Limitations

<!-- This section is meant to convey both technical and sociotechnical limitations. -->

- **Peer-Review Quality**: It is important to understand that while most sources are validated by internationally endorsed professional associations, a large proportion of articles are from Wikidoc which contains crowdsourced content. While edits in Wikidoc are generally restricted to expert review, the process of consensus and oversight is different from the traditional rigor of clinical guidelines.
- **Representation**: This corpus is in English, and over-represents English-speaking regions. While we have included WHO and ICRC guidelines for low-resource settings, further work needs to be done to scrape sources from diverse contexts.
- **Temporal scope**: Guidelines are constantly updated and these represent a snapshot of each in August 2023. Please re-scrape for updated content.

### Recommendations

<!-- This section is meant to convey recommendations with respect to the bias, risk, and technical limitations. -->

We warmly invite users to help us build a more representative corpus with high-quality peer-reviewed clinical practice guidelines in various languages and representing the full scope of clinical specialties and geographic regions.
We encourage users of this content to be mindful of its current limitations in temporal and geographic scope and we repeat our warning: creating tools that provide clinical advice is commendable, but extremely dangerous if not done with the appropriate care. Such tools need to be validated for safety and utility by medical professionals in randomized controlled trials. i.e. Please don’t create cowboy health apps that fool vulnerable users into thinking they are receiving validated advice.

## Acknowledgments

The availability of open-access clinical practice guidelines (CPG) was critical to this work, and we thank all the societies listed above. A broader representation of geography, medical specialties, and contexts (especially low-resource settings) could be achieved through more standardized CPG formatting practices to ensure reliable textual extraction (e.g., releasing `.txt` or `.html` versions with structured content). We encourage the CPG community to continue to make these documents available (open-access with permissive licenses for incorporation into large language models) and easily usable. 

## Authors

- **Curation**: Mary-Anne Hartley
- **Scraping**: Antoine Bonnet, Alexandre Sallinen, Igor Krawczuk, Kyle Matoba
- **Cleaning**: Antoine Bonnet, Alexandre Sallinen


## Citation

<!-- If there is a paper or blog post introducing the dataset, the APA and Bibtex information for that should go in this section. -->

If you use the Clinical Guidelines corpus, please cite out work:

```
@misc{chen2023meditron70b,
      title={MEDITRON-70B: Scaling Medical Pretraining for Large Language Models},
      author={Zeming Chen and Alejandro Hernández-Cano and Angelika Romanou and Antoine Bonnet and Kyle Matoba and Francesco Salvi and Matteo Pagliardini and Simin Fan and Andreas Köpf and Amirkeivan Mohtashami and Alexandre Sallinen and Alireza Sakhaeirad and Vinitra Swamy and Igor Krawczuk and Deniz Bayazit and Axel Marmet and Syrielle Montariol and Mary-Anne Hartley and Martin Jaggi and Antoine Bosselut},
      year={2023},
      eprint={2311.16079},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}

@software{epfmedtrn,
  author = {Zeming Chen and Alejandro Hernández-Cano and Angelika Romanou and Antoine Bonnet and Kyle Matoba and Francesco Salvi and Matteo Pagliardini and Simin Fan and Andreas Köpf and Amirkeivan Mohtashami and Alexandre Sallinen and Alireza Sakhaeirad and Vinitra Swamy and Igor Krawczuk and Deniz Bayazit and Axel Marmet and Syrielle Montariol and Mary-Anne Hartley and Martin Jaggi and Antoine Bosselut},
  title = {MediTron-70B: Scaling Medical Pretraining for Large Language Models},
  month = November,
  year = 2023,
  url = {https://github.com/epfLLM/meditron}
}
```