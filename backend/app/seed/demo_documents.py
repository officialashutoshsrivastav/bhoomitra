"""Synthetic demo documents for the Bhoomitra seed.

Every document is labelled Demo / Synthetic Data. Figures are illustrative and
must not be quoted as official statistics. Content is written to exercise the
ingestion, search, RAG and evidence pipelines with realistic domain vocabulary.
"""
from __future__ import annotations

from typing import Any, Dict, List

_HEADER = "DEMO / SYNTHETIC DATA — illustrative content prepared for platform demonstration. Figures are not official statistics.\n\n"

DEMO_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "title": "Digital India Land Records Modernisation Programme: Progress Review (Demo)",
        "document_type": "government_report",
        "topic": "land records",
        "policy_area": "land records",
        "geography": "Demo State 1",
        "publication_date": "2023-06-30",
        "authors": ["PME Division (Demo)"],
        "keywords": ["DILRMP", "land records", "digitisation", "cadastral maps", "record of rights"],
        "description": "Synthetic progress review of land record computerisation, cadastral map digitisation and registration integration in the demo states.",
        "text": """1. Background
The Digital India Land Records Modernisation Programme (DILRMP) seeks to build an integrated land information management system in which textual records, cadastral maps, registration and survey data are interoperable. In the demo dataset, computerisation of the record of rights reached 96 percent of villages across the six demo states by March 2023, while digitisation of cadastral maps stood at 81 percent.

2. Cadastral map digitisation
Digitisation of cadastral maps lagged behind textual records in every demo state. Demo State 3 reported the lowest coverage at 58 percent because legacy maps were stored on cloth and had deteriorated. Demo State 1 completed 99 percent of its map digitisation after adopting a district-level vendor model with quality gates: each sheet was checked for topological errors, area mismatch above two percent triggered field verification. Integration of textual and spatial records, which allows a survey number to be located on a map, was completed in 64 percent of villages.

3. Registration integration
Linking the registration system with the land record database enables automatic mutation when a sale deed is registered. In the demo states this integration reduced the median mutation time from 72 days to 19 days in integrated tehsils. Pending mutations older than ninety days fell by 41 percent over two years. Demo State 5 piloted an auto-mutation workflow in which the tehsildar receives a pre-filled mutation order and only exceptions require hearings.

4. Survey and resurvey
Modern survey using drones and continuously operating reference stations (CORS) was piloted in 140 demo villages. Drone surveys reduced the average per-village survey cost by 38 percent compared with electronic total station methods and cut boundary disputes recorded at the tehsil by 22 percent in pilot districts within eighteen months. Ground truthing remained necessary for about 9 percent of parcels where canopy or built-up density obscured boundaries.

5. Recommendations
The review recommends prioritising integration of textual and spatial records over further textual computerisation, establishing state-level cadastral map repositories with version control, adopting drone survey with CORS as the default for resurvey, and publishing district-wise dashboards of pending mutations. It also recommends a unified land parcel identification number to link records across departments.""",
    },
    {
        "title": "Watershed Development in Rain-fed Districts: Outcome Assessment (Demo)",
        "document_type": "research_paper",
        "topic": "watershed",
        "policy_area": "watershed",
        "research_area": "natural resource management",
        "geography": "Demo State 2",
        "publication_date": "2022-11-15",
        "authors": ["A. Demo", "B. Demo"],
        "keywords": ["watershed", "groundwater recharge", "rain-fed agriculture", "soil moisture", "check dams"],
        "description": "Synthetic evaluation of watershed treatment effects on groundwater, cropping intensity and incomes in rain-fed blocks.",
        "text": """Abstract
This synthetic study assesses watershed development projects in eight rain-fed blocks of Demo State 2 between 2015 and 2021. Treated micro-watersheds received contour trenching, farm ponds, check dams and drainage line treatment. Using a difference-in-differences design with untreated neighbouring micro-watersheds as controls, we estimate the effect of treatment on groundwater levels, cropping intensity and household income.

Findings
Post-monsoon groundwater levels in treated micro-watersheds rose by an average of 1.6 metres relative to controls. Cropping intensity increased from 118 percent to 139 percent in treated areas, driven mainly by a second crop of pulses and vegetables on farms within 300 metres of a farm pond. Annual household income from agriculture rose by 23 percent in treated villages against 6 percent in controls. Soil moisture measured at 30 centimetre depth in November was 4.2 percentage points higher in treated ridges.

Distribution of benefits
Benefits were concentrated in the middle and lower reaches of each watershed. Upper-reach farmers with shallow soils saw limited gains unless treatment included farm bunding. Landless households benefited primarily through wage employment during the construction phase and through increased fodder availability, which raised livestock income by 14 percent.

Maintenance and institutions
Structures maintained by watershed committees with a dedicated maintenance fund retained 87 percent of their storage capacity after five years, compared with 52 percent where no fund existed. Committees that met at least quarterly were more likely to resolve disputes over water sharing.

Policy implications
The results support prioritising watershed treatment in blocks with declining groundwater trends and cropping intensity below 125 percent. Convergence with employment guarantee works can finance construction while a maintenance fund financed by water user contributions sustains outcomes. Monitoring should use remotely sensed vegetation indices alongside groundwater observation wells.""",
    },
    {
        "title": "Wasteland Atlas Update and Reclamation Priorities (Demo)",
        "document_type": "technical_report",
        "topic": "wasteland",
        "policy_area": "wasteland",
        "geography": "All demo states",
        "publication_date": "2021-03-20",
        "authors": ["Demo Remote Sensing Cell"],
        "keywords": ["wasteland", "land degradation", "remote sensing", "reclamation", "salinity"],
        "description": "Synthetic mapping of wasteland categories from satellite imagery with reclamation priority ranking.",
        "text": """Purpose
This synthetic technical report updates the wasteland inventory for the six demo states using multi-date satellite imagery at 10 metre resolution. Wasteland categories follow a thirteen-class scheme including gullied land, land with dense scrub, land with open scrub, waterlogged and marshy land, salt-affected land, degraded forest, mining wasteland and barren rocky areas.

Extent and change
Total wasteland in the demo states was mapped at 41,200 square kilometres, a decrease of 5.8 percent since the previous demo cycle. The largest reductions occurred in land with open scrub, which was brought under cultivation or plantation, and in gullied land treated under watershed programmes. Salt-affected land increased by 3.1 percent, concentrated in canal command areas of Demo State 4 where waterlogging raised the water table and evaporation left salt crusts.

Methodology
Classification combined a normalised difference vegetation index time series with a soil-adjusted index and a built-up index. Training samples were collected from field visits in 312 locations. Overall classification accuracy in the demo validation set was 86 percent, with lowest accuracy for the distinction between land with open scrub and degraded pasture.

Reclamation priorities
Reclamation priority was ranked by combining the wasteland category, proximity to villages, slope and rainfall. High-priority parcels are those within three kilometres of a village, on slopes below eight percent, in areas receiving more than 600 millimetres of rainfall. Under these criteria 6,400 square kilometres qualify for plantation or silvipasture, and 2,100 square kilometres of salt-affected land qualify for subsurface drainage and gypsum treatment.

Limitations
The inventory does not capture seasonal wasteland such as fallow that is cultivated in alternate years. Cloud cover during the monsoon limited the number of usable scenes in Demo State 6. Class boundaries should be verified in the field before allotment decisions.""",
    },
    {
        "title": "Land Acquisition, Rehabilitation and Resettlement: Implementation Case Studies (Demo)",
        "document_type": "case_study",
        "topic": "land acquisition",
        "policy_area": "land acquisition",
        "geography": "Demo State 3",
        "publication_date": "2020-09-10",
        "authors": ["Demo Policy Research Unit"],
        "keywords": ["land acquisition", "compensation", "rehabilitation", "resettlement", "social impact assessment"],
        "description": "Synthetic case studies of acquisition for infrastructure projects covering compensation, consent and rehabilitation outcomes.",
        "text": """Introduction
These synthetic case studies examine four acquisition processes for road, irrigation and industrial projects in Demo State 3. Each case documents the social impact assessment, the consent process, compensation determination and the rehabilitation package.

Case A: Highway widening
Acquisition of 84 hectares affected 610 families. Compensation was set at twice the market value in rural areas with a solatium, and the average award was disbursed within 14 months. Delays arose mainly from disputed ownership in 12 percent of parcels where mutation had not been recorded after inheritance. Families that received compensation through direct bank transfer reported higher satisfaction than those paid through cheques.

Case B: Irrigation reservoir
The reservoir submerged three villages and displaced 1,240 families. Resettlement colonies were established with house plots, drinking water and a school. Three years after resettlement, 68 percent of households reported income at or above pre-displacement levels; fishing rights in the reservoir were an important source of livelihood for landless families. Households resettled more than 20 kilometres from their original land reported the largest income losses.

Case C: Industrial park
Consent of 80 percent of affected families was obtained through gram sabha resolutions after two rounds of consultation. A land pooling alternative, in which owners retained a developed plot equal to 25 percent of contributed area, was preferred by owners of small holdings.

Case D: Transmission line
Right-of-way compensation for tower footprints and corridor restrictions was contested because corridor land remained with owners but lost value. The case suggests a standard compensation formula for diminution of value under transmission corridors.

Lessons
Complete and updated land records are the single largest determinant of acquisition timelines. Rehabilitation packages that preserve proximity to original livelihoods perform better than distant resettlement. Land pooling reduces conflict where land values are expected to rise after development.""",
    },
    {
        "title": "SVAMITVA-style Property Card Survey in Inhabited Village Areas: Lessons (Demo)",
        "document_type": "policy_paper",
        "topic": "land records",
        "policy_area": "land records",
        "geography": "Demo State 1",
        "publication_date": "2023-01-12",
        "authors": ["Demo Survey Directorate"],
        "keywords": ["property card", "abadi", "drone survey", "village settlement", "tenure security"],
        "description": "Synthetic policy paper on drone-based surveying of inhabited village areas and issuing property cards.",
        "text": """Context
Inhabited village areas (abadi) were historically excluded from cadastral survey, leaving households without documentary title to their homestead. A drone-based survey generating ortho-rectified maps at five centimetre resolution enables demarcation of individual properties and issuance of property cards.

Process
Village boundaries were verified with residents and the ground control network established using CORS. Drones captured imagery in a single day for a typical village of 300 properties. Feature extraction identified building footprints and plot boundaries, which were verified through a public display of the draft map and an objection period of thirty days. In the demo dataset, 4.7 percent of properties received objections, most commonly over shared walls and encroachment on village common land.

Outcomes
Property cards were issued to 218,000 households across the demo states. Card holders were able to use the card as collateral for loans; 11 percent of card holders obtained a bank loan within two years compared with 3 percent of comparable households without cards. Property tax collection by gram panchayats increased where cards were linked to the tax register.

Challenges
Disputes over common land encroachment required a policy decision on regularisation cut-off dates. Women's names appeared as sole or joint owners on 31 percent of cards; targeted awareness campaigns raised this to 44 percent in Demo State 1. Updating cards after inheritance or sale requires integration with the registration system, which remains incomplete.

Recommendations
Adopt a statutory basis for property cards, define encroachment regularisation rules before survey, integrate cards with registration and property tax systems, and mandate joint titling options at issuance.""",
    },
    {
        "title": "Groundwater Stress and Land Use Change in Canal Command Areas (Demo)",
        "document_type": "research_paper",
        "topic": "water",
        "policy_area": "water",
        "research_area": "hydrology",
        "geography": "Demo State 4",
        "publication_date": "2022-04-05",
        "authors": ["C. Demo"],
        "keywords": ["groundwater", "canal command", "waterlogging", "salinity", "cropping pattern"],
        "description": "Synthetic analysis linking canal irrigation expansion, cropping pattern shifts and groundwater dynamics.",
        "text": """Summary
This synthetic study links canal irrigation expansion in Demo State 4 with changes in cropping pattern and groundwater. Between 2010 and 2020 the area under water-intensive crops in the command area increased by 27 percent. In the head reach, over-application of canal water raised the water table by 0.4 metres per year, leading to waterlogging on 5 percent of the command area, while tail-reach farmers relied on tubewells and experienced a decline of 0.9 metres per year.

Land use change
Satellite classification shows conversion of 310 square kilometres of grassland and scrub into cropland within the command area, and the appearance of 48 square kilometres of waterlogged land near the main canal. Built-up area along the canal road grew by 62 percent.

Salinity
Electrical conductivity of shallow groundwater exceeded four decisiemens per metre in 18 percent of sampled wells in the head reach. Salt-affected patches reduced wheat yields by an estimated 22 percent in the affected fields.

Policy implications
Volumetric water pricing, rotational canal supply and conjunctive use of surface and groundwater are recommended. Land use zoning should prevent the conversion of natural drainage lines and restrict construction on flood-prone canal margins. Subsurface drainage in waterlogged patches has a payback period of six years in the demo cost model.""",
    },
    {
        "title": "Guidelines for Land Use Zoning in Peri-urban Areas (Demo)",
        "document_type": "guideline",
        "topic": "urban",
        "policy_area": "urban",
        "geography": "All demo states",
        "publication_date": "2021-08-01",
        "authors": ["Demo Town and Country Planning Cell"],
        "keywords": ["land use zoning", "peri-urban", "master plan", "agricultural land conversion", "green belt"],
        "description": "Synthetic guidelines for zoning peri-urban land, controlling agricultural land conversion and protecting water bodies.",
        "text": """Objective
These synthetic guidelines provide a framework for zoning land within ten kilometres of municipal boundaries, where agricultural land conversion, unplanned layouts and loss of water bodies are most acute.

Zoning categories
Six categories are defined: agricultural conservation, water body and buffer, green belt, planned residential, industrial and logistics, and institutional. Water bodies receive a mandatory buffer of thirty metres for ponds and fifty metres for rivers within which construction is prohibited. Agricultural conservation zones cover irrigated land with cropping intensity above 150 percent.

Conversion procedure
Conversion of agricultural land requires a land use change permission linked to the master plan. Applications are decided within sixty days and published online. Conversion charges are set at a percentage of the circle rate and earmarked for a peri-urban infrastructure fund.

Monitoring
Annual change detection using satellite imagery identifies unauthorised conversion. In the demo pilot, 2,150 hectares of unauthorised layouts were detected in two years, of which 38 percent were regularised with penalties and infrastructure contributions and the remainder restored or acquired.

Implementation lessons
Zoning is effective only when master plans are notified with parcel-level maps and integrated with the registration system so that a sale deed for a non-permitted use cannot be registered. Transfer of development rights helps compensate owners of land in conservation zones.""",
    },
    {
        "title": "Forest Rights Recognition and Community Forest Resource Management (Demo)",
        "document_type": "working_paper",
        "topic": "forest",
        "policy_area": "forest",
        "research_area": "tenure",
        "geography": "Demo State 5",
        "publication_date": "2019-12-01",
        "authors": ["D. Demo", "E. Demo"],
        "keywords": ["forest rights", "community forest resource", "tenure", "tribal", "conservation"],
        "description": "Synthetic working paper on individual and community forest rights recognition and conservation outcomes.",
        "text": """Overview
This synthetic paper reviews the recognition of individual and community forest rights in Demo State 5 and the management of community forest resources by gram sabhas. In the demo dataset, 61 percent of individual claims and 34 percent of community claims were recognised; rejected claims were concentrated in villages lacking documentary evidence of occupation.

Conservation outcomes
Villages with recognised community forest resource rights showed a 3 percent increase in canopy density over five years compared with a 1 percent decrease in adjoining villages without rights. Gram sabhas that prepared management plans regulated grazing, controlled fires and earned income from minor forest produce, which rose by 38 percent.

Livelihoods
Household income from minor forest produce averaged 27 percent of total income in villages with recognised rights. Collective marketing through federations raised prices received by 15 to 20 percent.

Constraints
Delays in demarcation of community forest resource boundaries and lack of integration with forest department working plans limited management. Maps prepared by gram sabhas were often not accepted because they were not on the cadastral base.

Recommendations
Provide cadastral base maps and geospatial support to gram sabhas, recognise community forest resource rights in convergence with watershed programmes, and align forest working plans with community management plans.""",
    },
    {
        "title": "Climate-resilient Land Use Planning for Flood-prone Districts (Demo)",
        "document_type": "framework",
        "topic": "climate",
        "policy_area": "disaster",
        "geography": "Demo State 6",
        "publication_date": "2023-03-15",
        "authors": ["Demo Climate Cell"],
        "keywords": ["flood", "climate resilience", "land use planning", "hazard zoning", "wetlands"],
        "description": "Synthetic framework for integrating flood hazard mapping into district land use plans.",
        "text": """Rationale
Flood-prone districts in Demo State 6 experienced three major floods between 2017 and 2022 affecting 18 percent of the cultivated area. Encroachment on floodplains, filling of wetlands and construction on natural drainage lines increased damage.

Hazard zoning
Flood hazard zones were mapped by combining historical inundation extents from satellite imagery, a digital elevation model and hydrological modelling for ten and hundred year return periods. Zone A (annual inundation) is reserved for wetlands, grazing and seasonal cropping; Zone B (ten year) permits agriculture and flood-resilient infrastructure; Zone C (hundred year) permits regulated construction with elevated plinths.

Wetland restoration
Restoring 120 hectares of wetlands in the demo pilot increased flood storage by 2.1 million cubic metres and reduced peak flows downstream by 8 percent in the model. Wetlands also supported fisheries income for 340 households.

Land use decisions
District land use plans should embed hazard zones as statutory layers, prohibit conversion of wetlands, and prioritise relocation incentives for households in Zone A. Crop insurance premiums can be differentiated by zone to reflect risk.

Uncertainty
Climate projections indicate a 10 to 20 percent increase in extreme rainfall intensity; hazard zones should be revised every five years. Model outputs carry uncertainty and should be labelled as modelled estimates in planning documents.""",
    },
    {
        "title": "Tenancy Reform and Land Leasing: Evidence from Demo States",
        "document_type": "policy_paper",
        "topic": "tenure",
        "policy_area": "tenure",
        "geography": "Demo State 2",
        "publication_date": "2020-02-20",
        "authors": ["Demo Institute of Rural Studies"],
        "keywords": ["tenancy", "land leasing", "tenure security", "sharecropping", "credit access"],
        "description": "Synthetic policy analysis of formalising agricultural land leasing and its effects on investment and credit.",
        "text": """Issue
Informal leasing of agricultural land is widespread but tenants lack security and access to credit, insurance and input subsidies. A model leasing framework that records lease agreements without conferring ownership claims was piloted in Demo State 2.

Evidence
Recorded leases rose from 4 percent to 29 percent of leased area in pilot districts within three years. Tenants with recorded leases invested 18 percent more in soil improvement and were twice as likely to obtain crop loans. Owners reported greater willingness to lease long term because the record protected their ownership.

Distributional effects
Small and marginal farmers leasing in land benefited the most; women-headed households leasing out land gained a documented income stream. Rents rose modestly by 6 percent, reflecting the value of security.

Implementation
Lease records were maintained in the land record system as a separate register without altering the record of rights. Disputes were resolved by revenue officers within sixty days in 82 percent of cases.

Recommendation
Extend the model framework, link recorded leases to credit and insurance eligibility, and monitor rent trends to protect tenants.""",
    },
    {
        "title": "Remote Sensing Protocol for Annual Land Use Land Cover Monitoring (Demo)",
        "document_type": "technical_report",
        "topic": "remote sensing",
        "policy_area": "land use",
        "research_area": "geospatial",
        "geography": "All demo states",
        "publication_date": "2022-07-01",
        "authors": ["Demo Remote Sensing Cell"],
        "keywords": ["remote sensing", "land use land cover", "NDVI", "change detection", "classification"],
        "description": "Synthetic protocol describing indices, classification thresholds and validation for annual LULC monitoring.",
        "text": """Purpose
This synthetic protocol standardises annual land use land cover monitoring from multispectral satellite imagery for the demo states.

Indices
The normalised difference vegetation index is computed as (NIR - Red) / (NIR + Red). The normalised difference water index uses (Green - NIR) / (Green + NIR) and the normalised difference built-up index uses (SWIR - NIR) / (SWIR + NIR). Composites use the median of cloud-free observations in the post-monsoon window.

Classification
A rule-based classifier assigns water where NDWI exceeds 0.2, built-up where NDBI exceeds 0.05 and NDVI is below 0.3, dense vegetation where NDVI exceeds 0.6, cropland where NDVI is between 0.4 and 0.6, sparse vegetation between 0.2 and 0.4, and barren otherwise. Thresholds are calibrated per agro-climatic zone using field samples.

Change detection
Annual change is computed as the difference in NDVI composites; a decrease greater than 0.15 flags vegetation loss and an increase greater than 0.15 flags gain. A transition matrix between classes quantifies conversions such as cropland to built-up.

Validation
Validation uses stratified random samples of 100 points per class. Overall accuracy in the demo validation exercise was 84 percent; built-up and barren classes were most frequently confused in dry regions.

Outputs
Products include class maps, area statistics by administrative unit and change maps. All products are labelled as modelled estimates with stated accuracy.""",
    },
    {
        "title": "Land Pooling as an Alternative to Acquisition: Design Options (Demo)",
        "document_type": "policy_paper",
        "topic": "land acquisition",
        "policy_area": "land acquisition",
        "geography": "Demo State 3",
        "publication_date": "2021-11-30",
        "authors": ["Demo Policy Research Unit"],
        "keywords": ["land pooling", "town planning scheme", "readjustment", "infrastructure financing"],
        "description": "Synthetic comparison of land pooling schemes for urban expansion and industrial development.",
        "text": """Concept
Land pooling assembles contiguous parcels, provides infrastructure and returns a proportion of developed land to the original owners. Owners share in the appreciation while the authority obtains land for roads, utilities and public purposes without cash acquisition.

Design parameters
The return ratio in the demo schemes ranged from 40 to 60 percent of contributed area. Schemes with a return ratio below 45 percent faced resistance unless the developed land value exceeded three times the pre-scheme value. Betterment charges financed 30 to 50 percent of infrastructure costs.

Timelines
Demo schemes took four to seven years from notification to plot allotment. The longest delays occurred in verification of ownership, indicating again the importance of updated land records.

Equity considerations
Landless residents and tenants do not receive developed plots; the demo schemes that reserved 5 percent of land for affordable housing and a livelihood fund had higher acceptance. Small owners preferred consolidated plots over multiple fragments.

Recommendations
Publish a standard return ratio formula, mandate a social impact component, integrate the scheme with the registration system so that pooled parcels are flagged, and adopt a dispute resolution mechanism with fixed timelines.""",
    },
]
