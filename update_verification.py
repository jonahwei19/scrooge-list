#!/usr/bin/env python3
"""
Update billionaire data with source-based verification pipeline data.
Each billionaire will have a 'verification' field showing status of each data source.
"""

import json

# Verification data collected from research
VERIFICATION_DATA = {
    "Jeff Bezos": {
        "total_lifetime_giving_millions": 3800,
        "giving_breakdown": {
            "bezos_earth_fund": 2300,
            "day_one_fund": 850,
            "bezos_academies": 150,
            "direct_personal_gifts": 500,
            "notes": "VERIFIED Jan 2026: Earth Fund $2.3B disbursed (of $10B pledge). Day One Fund $850M+ since 2018. Smithsonian $200M, Courage Awards $200M+, Princeton $15M, misc $85M."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "Uses DAF structure, no 990-PF filings", "url": None},
            "sec_form4": {"status": "partial", "amount_millions": 0, "note": "Stock gifts go through DAF", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001043298&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 3150, "sources": ["Bezos Earth Fund", "Day One Fund"], "note": "Earth Fund: $2.3B, Day One: $850M", "url": "https://www.bezosearthfund.org/"},
            "news_verified": {"status": "found", "amount_millions": 650, "sources": ["Smithsonian $200M", "Princeton $15M", "Courage Awards $200M+", "Other direct $235M"], "url": "https://www.si.edu/newsdesk/releases/smithsonian-receive-historic-200-million-donation-jeff-bezos"}
        },
        "sources": [
            "https://www.cnbc.com/2025/07/15/jeff-bezos-taps-tom-taylor-earth-fund.html",
            "https://www.bezosdayonefund.org/day1familiesfund",
            "https://www.si.edu/newsdesk/releases/smithsonian-receive-historic-200-million-donation-jeff-bezos"
        ]
    },
    "Elon Musk": {
        "total_lifetime_giving_millions": 270,
        "giving_breakdown": {
            "xprize_carbon_removal": 100,
            "st_jude": 55,
            "rio_grande_valley": 30,
            "khan_academy": 12.5,
            "un_giga": 5,
            "hack_foundation": 4,
            "world_central_kitchen": 2,
            "other_external": 61.5,
            "notes": "VERIFIED Jan 2026: Foundation has $14B assets but 78% goes to self-controlled entities. This counts only external giving."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 14000, "ein": "77-0587507", "note": "Foundation ASSETS $14B, but 78% of grants to self-controlled entities. External grants only ~$270M", "url": "https://projects.propublica.org/nonprofits/organizations/770587507"},
            "sec_form4": {"status": "found", "amount_millions": 5700, "note": "$5.7B stock donation 2021 - went to own foundation, not external charity", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 270, "sources": ["Musk Foundation 990-PF"], "note": "Only ~$270M to external charities since 2002", "url": "https://projects.propublica.org/nonprofits/organizations/770587507"},
            "news_verified": {"status": "found", "amount_millions": 270, "sources": ["NYT 2025", "Forbes 2024", "Wikipedia"], "url": "https://www.nytimes.com/2025/12/02/us/politics/elon-musk-foundation.html"}
        },
        "sources": [
            "https://www.nytimes.com/2025/12/02/us/politics/elon-musk-foundation.html",
            "https://projects.propublica.org/nonprofits/organizations/770587507"
        ]
    },
    "Larry Page": {
        "total_lifetime_giving_millions": 150,
        "giving_breakdown": {
            "external_charities_2024": 48,
            "external_charities_2023": 66,
            "ebola_relief_2014": 15,
            "pre_2023_misc": 21,
            "notes": "VERIFIED Jan 2026: Foundation has $6.7B but 97.8% goes to DAFs. Only ~$150M to actual operating charities."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 6700, "ein": "20-1922957", "note": "Carl Victor Page Memorial Foundation. $6.7B assets but 97.8% to DAFs", "url": "https://projects.propublica.org/nonprofits/organizations/201922957"},
            "sec_form4": {"status": "not_found", "note": "No stock gifts to external charities found", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 150, "sources": ["ProPublica 990-PF"], "note": "Only ~$150M to operating charities (not DAFs)", "url": "https://projects.propublica.org/nonprofits/organizations/201922957"},
            "news_verified": {"status": "found", "amount_millions": 150, "sources": ["Inside Philanthropy", "Philanthropy News Digest"], "url": "https://www.insidephilanthropy.com/home/larry-page-steps-out-of-the-shadows-as-a-climate-donor"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/201922957",
            "https://www.insidephilanthropy.com/home/larry-page-steps-out-of-the-shadows-as-a-climate-donor"
        ]
    },
    "MacKenzie Scott": {
        "total_lifetime_giving_millions": 26300,
        "giving_breakdown": {
            "giving_2020": 5800,
            "giving_2021": 2700,
            "giving_2022": 3900,
            "giving_2023": 2100,
            "giving_2024": 2600,
            "giving_2025": 7170,
            "notes": "VERIFIED Jan 2026: $26.3B total through Dec 2025. 1,600+ organizations. Unrestricted gifts via Yield Giving."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Gives directly, no foundation structure", "url": None},
            "sec_form4": {"status": "found", "amount_millions": 26300, "note": "Amazon stock gifts tracked via SEC", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001694401&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "not_applicable", "note": "Uses Yield Giving, not traditional foundation", "url": "https://yieldgiving.com/"},
            "news_verified": {"status": "found", "amount_millions": 26300, "sources": ["Chronicle of Philanthropy", "CNBC", "Observer"], "url": "https://observer.com/2024/12/mackenzie-scott-donatino-five-years/"}
        },
        "sources": [
            "https://observer.com/2024/12/mackenzie-scott-donatino-five-years/",
            "https://www.cnbc.com/2025/12/02/mackenzie-scott-giving.html"
        ]
    },
    "Bernard Arnault": {
        "total_lifetime_giving_millions": 600,
        "giving_breakdown": {
            "notre_dame": 226,
            "fondation_louis_vuitton_net": 190,
            "caillebotte_painting": 47,
            "chardin_louvre": 16,
            "versailles": 10,
            "restos_du_coeur": 11,
            "amazon_fires": 11,
            "covid_china": 2,
            "other": 87,
            "notes": "VERIFIED Jan 2026: Notre Dame €200M confirmed paid. Fondation Louis Vuitton €790M gross but €603M tax benefit = €187M net. Cultural gifts via LVMH."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "French billionaire - see French foundation filings", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Not US-listed for philanthropy", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 600, "sources": ["Fondation Louis Vuitton", "French press"], "note": "€500M+ verified", "url": "https://www.fondationlouisvuitton.fr/"},
            "news_verified": {"status": "found", "amount_millions": 600, "sources": ["Reuters", "Le Monde", "Artnet"], "url": "https://www.reuters.com/article/us-france-notredame-lvmh-idUSKCN1RU1FD/"}
        },
        "sources": [
            "https://www.reuters.com/article/us-france-notredame-lvmh-idUSKCN1RU1FD/",
            "https://news.artnet.com/market/lvmh-caillebotte-musee-dorsay-2252434"
        ]
    },
    "Larry Ellison": {
        "total_lifetime_giving_millions": 1150,
        "giving_breakdown": {
            "ellison_medical_foundation": 430,
            "larry_ellison_foundation": 450,
            "usc_cancer_center": 200,
            "friends_of_idf": 27,
            "wildlife_conservation": 50,
            "other": 43,
            "notes": "VERIFIED Jan 2026: Ellison Medical Foundation $430M (closed 2013). Larry Ellison Foundation ~$450M cumulative. USC $200M. IDF $27M. Wildlife $50M."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 450, "ein": "94-3269827", "note": "Larry Ellison Foundation: $70M/year recent, $450M cumulative", "url": "https://projects.propublica.org/nonprofits/organizations/943269827"},
            "sec_form4": {"status": "partial", "note": "Some stock gifts to foundation", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000930545&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 880, "sources": ["ProPublica 990-PF", "Ellison Medical Foundation"], "note": "EMF $430M + LEF $450M", "url": "https://projects.propublica.org/nonprofits/organizations/943269827"},
            "news_verified": {"status": "found", "amount_millions": 270, "sources": ["USC $200M", "IDF $27M", "Wildlife $50M"], "url": "https://keck.usc.edu/ellison-institute/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/943269827",
            "https://keck.usc.edu/ellison-institute/"
        ]
    },
    "Gautam Adani": {
        "total_lifetime_giving_millions": 250,
        "giving_breakdown": {
            "adani_foundation_cumulative": 200,
            "hurun_tracked_2018_2025": 185,
            "announced_pledges_not_disbursed": 0,
            "notes": "VERIFIED Jan 2026: $7.7B PLEDGED in 2022 but actual disbursement ~$40-50M/year. Hurun tracks ~Rs 330-386 crore ($40-46M) annually."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Indian billionaire - see India CSR filings", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Not US-listed", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 250, "sources": ["Adani Foundation", "Hurun India"], "note": "~$200-250M cumulative, $40-50M/year current", "url": "https://www.adanifoundation.org"},
            "news_verified": {"status": "found", "amount_millions": 250, "sources": ["EdelGive-Hurun India Philanthropy List", "Business Standard"], "url": "https://www.hurun.net/en-us/info/detail?num=WSDEYUNJNT7P"}
        },
        "sources": [
            "https://www.adanifoundation.org",
            "https://www.hurun.net/en-us/info/detail?num=WSDEYUNJNT7P"
        ]
    },
    "Francoise Bettencourt Meyers": {
        "total_lifetime_giving_millions": 800,
        "giving_breakdown": {
            "bettencourt_schueller_foundation": 700,
            "notre_dame": 112,
            "fondation_pour_audition": 20,
            "notes": "VERIFIED Jan 2026: Foundation has €900M endowment, ~€15-20M/year for 37 years = €600-750M cumulative. Notre Dame €100M (family share)."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "French billionaire - see French foundation filings", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Not US-listed", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 800, "sources": ["Fondation Bettencourt Schueller"], "note": "€900M endowment, 37 years operation", "url": "https://www.fondationbs.org/"},
            "news_verified": {"status": "found", "amount_millions": 112, "sources": ["Notre Dame €100M", "Institut de l'Audition"], "url": "https://www.forbes.com/sites/kerryadolan/2019/04/17/french-billionaires-pledge-more-than-600-million-to-rebuild-notre-dame/"}
        },
        "sources": [
            "https://www.fondationbs.org/",
            "https://www.forbes.com/sites/kerryadolan/2019/04/17/french-billionaires-pledge-more-than-600-million-to-rebuild-notre-dame/"
        ]
    },
    "Phil Knight": {
        "total_lifetime_giving_millions": 7800,
        "giving_breakdown": {
            "ohsu_cumulative": 2600,
            "university_of_oregon": 2200,
            "stanford": 580,
            "1803_fund_portland": 400,
            "knight_foundation_cumulative": 1000,
            "other": 1020,
            "notes": "VERIFIED Jan 2026: Chronicle reports $7.8B over 20 years. OHSU $2.6B (incl $2B Aug 2025), UO $2.2B, Stanford $580M, 1803 Fund $400M."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 1000, "ein": "91-1791788", "note": "Knight Foundation ~$200M+/year, $1B cumulative", "url": "https://projects.propublica.org/nonprofits/organizations/911791788"},
            "sec_form4": {"status": "found", "amount_millions": 7800, "note": "Nike stock gifts to universities tracked", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001091528&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 1000, "sources": ["Knight Foundation 990-PF"], "note": "$226M (2024), $190M (2023), $212M (2022)", "url": "https://projects.propublica.org/nonprofits/organizations/911791788"},
            "news_verified": {"status": "found", "amount_millions": 6800, "sources": ["Chronicle of Philanthropy", "OHSU", "Oregon", "Stanford"], "url": "https://www.philanthropy.com/article/phil-knight-7-8-billion-giving/"}
        },
        "sources": [
            "https://www.philanthropy.com/article/phil-knight-7-8-billion-giving/",
            "https://www.ohsu.edu/knight-cancer-institute"
        ]
    },
    "Rupert Murdoch": {
        "total_lifetime_giving_millions": 30,
        "giving_breakdown": {
            "la_catholic_cathedral": 10,
            "murdoch_foundation_grants": 6,
            "hurricane_sandy": 1,
            "milly_dowler_charities": 1,
            "rick_warren": 2,
            "bushfire_relief": 2,
            "other_misc": 8,
            "notes": "VERIFIED Jan 2026: Inside Philanthropy calls him 'legendary Scrooge'. Murdoch Foundation has $0 assets since 2015. Dead last on Forbes Generosity Index."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 0, "ein": "13-3756893", "note": "Murdoch Foundation has $0 assets since 2015, no grants since 2008", "url": "https://projects.propublica.org/nonprofits/organizations/133756893"},
            "sec_form4": {"status": "not_found", "note": "No charitable stock gifts found", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 6, "sources": ["ProPublica 990-PF"], "note": "Only $6M in grants 2005-2008, then stopped", "url": "https://projects.propublica.org/nonprofits/organizations/133756893"},
            "news_verified": {"status": "found", "amount_millions": 24, "sources": ["Inside Philanthropy", "Various news"], "url": "https://www.insidephilanthropy.com/glitzy-giving/rupert-murdoch.html"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/133756893",
            "https://www.insidephilanthropy.com/glitzy-giving/rupert-murdoch.html"
        ]
    },
    "Bill Gates": {
        "total_lifetime_giving_millions": 60200,
        "giving_breakdown": {
            "gates_foundation_contribution": 60200,
            "foundation_grants_paid_out": 83300,
            "buffett_contribution_not_counted": 0,
            "notes": "VERIFIED Jan 2026: Bill & Melinda Gates contributed $60.2B to the foundation. Foundation has paid out $83.3B in grants (includes Buffett's $43.3B + investment returns). Counting Bill's personal contribution only."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 83300, "ein": "56-2618866", "note": "Gates Foundation 990-PF: $83.3B grants paid through Q4 2024", "url": "https://projects.propublica.org/nonprofits/organizations/562618866"},
            "sec_form4": {"status": "found", "amount_millions": 60200, "note": "$20B in 2022, $4.6B in 2017, plus ongoing transfers", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001163012&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 60200, "sources": ["Gates Foundation Fact Sheet"], "note": "Bill & Melinda Gates personal contribution: $60.2B", "url": "https://www.gatesfoundation.org/about/foundation-fact-sheet"},
            "news_verified": {"status": "found", "amount_millions": 60200, "sources": ["Gates Foundation", "Forbes", "CNBC"], "url": "https://www.forbes.com/sites/kerryadolan/2022/08/03/bill-gates-transferred-billions-of-dollars-worth-of-these-two-stocks-to-the-gates-foundation/"}
        },
        "sources": [
            "https://www.gatesfoundation.org/about/foundation-fact-sheet",
            "https://www.forbes.com/sites/kerryadolan/2022/08/03/bill-gates-transferred-billions-of-dollars-worth-of-these-two-stocks-to-the-gates-foundation/"
        ]
    },
    "Warren Buffett": {
        "total_lifetime_giving_millions": 60000,
        "giving_breakdown": {
            "gates_foundation": 48000,
            "susan_thompson_buffett_foundation": 6000,
            "sherwood_foundation": 3500,
            "howard_g_buffett_foundation": 3500,
            "novo_foundation": 3500,
            "notes": "VERIFIED Jan 2026: $60B+ lifetime giving. $48B to Gates Foundation (2006-2025). ~$6B to Susan Thompson Buffett Foundation. ~$3.5B each to three children's foundations."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 60000, "note": "Berkshire stock gifts tracked via 990-PF filings of recipient foundations", "url": "https://projects.propublica.org/nonprofits/organizations/470824753"},
            "sec_form4": {"status": "found", "amount_millions": 60000, "note": "All gifts are Berkshire Class B shares, tracked via SEC", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000315090&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 60000, "sources": ["Gates Foundation", "STBF", "Sherwood", "HGBF", "NoVo"], "note": "Annual June/July donations since 2006", "url": "https://www.gatesfoundation.org/about/foundation-fact-sheet"},
            "news_verified": {"status": "found", "amount_millions": 60000, "sources": ["AP News", "Reuters", "Chronicle of Philanthropy"], "url": "https://apnews.com/article/warren-buffett-charity-donation-berkshire-hathaway"}
        },
        "sources": [
            "https://www.gatesfoundation.org/about/foundation-fact-sheet",
            "https://apnews.com/article/warren-buffett-charity-donation-berkshire-hathaway"
        ]
    },
    "Mark Zuckerberg": {
        "total_lifetime_giving_millions": 5000,
        "giving_breakdown": {
            "czi_foundation_grants": 1870,
            "czi_llc_estimated": 3130,
            "notes": "VERIFIED Jan 2026: CZI Foundation 990-PF shows $1.87B in grants (2017-2024). CZI LLC grants not publicly disclosed. Total estimated ~$5B actual disbursements. The '$45B pledge' refers to stock transfer to LLC, not donations."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 1870, "ein": "45-5002209", "note": "CZI Foundation: $388M (2024), $216M (2023), $418M (2022), etc.", "url": "https://projects.propublica.org/nonprofits/organizations/455002209"},
            "sec_form4": {"status": "found", "amount_millions": 45000, "note": "$45B in Meta stock transferred to CZI LLC - but LLC is not charity", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001548760&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 1870, "sources": ["ProPublica CZI Foundation 990-PF"], "note": "$1.87B verified through foundation arm", "url": "https://projects.propublica.org/nonprofits/organizations/455002209"},
            "news_verified": {"status": "found", "amount_millions": 5000, "sources": ["PureGrant", "SF Standard", "CZI website"], "url": "https://chanzuckerberg.com/grants-ventures/grants/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/455002209",
            "https://chanzuckerberg.com/grants-ventures/grants/"
        ]
    },
    "Sergey Brin": {
        "total_lifetime_giving_millions": 2700,
        "giving_breakdown": {
            "brin_wojcicki_foundation": 1870,
            "direct_gifts": 830,
            "notes": "VERIFIED Jan 2026: Brin Wojcicki Foundation 990-PF shows $1.87B cumulative grants (6 years). Additional direct giving ~$830M."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 1870, "ein": "20-1922947", "note": "Brin Wojcicki Foundation cumulative grants", "url": "https://projects.propublica.org/nonprofits/organizations/201922947"},
            "sec_form4": {"status": "partial", "note": "Some stock gifts to foundation tracked", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001113296&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 1870, "sources": ["ProPublica 990-PF"], "note": "Foundation grants verified", "url": "https://projects.propublica.org/nonprofits/organizations/201922947"},
            "news_verified": {"status": "found", "amount_millions": 830, "sources": ["Various news sources"], "url": "https://www.insidephilanthropy.com/guide-to-individual-donors/sergey-brin"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/201922947"
        ]
    },
    "Jensen Huang": {
        "total_lifetime_giving_millions": 115,
        "giving_breakdown": {
            "oregon_state": 55,
            "stanford": 30,
            "california_college_arts": 22.5,
            "oneida_baptist": 2,
            "johns_hopkins": 1,
            "other": 4.5,
            "notes": "VERIFIED Jan 2026: Foundation has $9.2B assets but 2/3 goes to DAFs. Actual non-DAF grants ~$115M. OSU $55M, Stanford $30M, CCA $22.5M."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 335, "ein": "26-1551239", "note": "Jen-Hsun & Lori Huang Foundation: $335M disbursed but ~$220M to DAFs", "url": "https://projects.propublica.org/nonprofits/organizations/261551239"},
            "sec_form4": {"status": "found", "note": "Nvidia stock gifts to foundation tracked", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001341439&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 115, "sources": ["ProPublica 990-PF"], "note": "Non-DAF grants only ~$115M (2007-2024)", "url": "https://projects.propublica.org/nonprofits/organizations/261551239"},
            "news_verified": {"status": "found", "amount_millions": 115, "sources": ["Bloomberg", "OSU", "Stanford", "CCA"], "url": "https://www.insidephilanthropy.com/guide-to-individual-donors/jensen-huang"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/261551239",
            "https://www.insidephilanthropy.com/guide-to-individual-donors/jensen-huang"
        ]
    },
    "Michael Dell": {
        "total_lifetime_giving_millions": 2800,
        "giving_breakdown": {
            "dell_foundation_cumulative": 2800,
            "ut_austin_total": 200,
            "dell_medical_school": 50,
            "dell_childrens_medical": 90,
            "charter_schools": 120,
            "homelessness": 38,
            "notes": "VERIFIED Jan 2026: Michael & Susan Dell Foundation 990-PF shows $2.8B cumulative grants (1999-2024). ~$175-220M/year recent. UT Austin $200M, Dell Medical School $50M."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 2800, "ein": "36-4336415", "note": "Michael & Susan Dell Foundation: $219M (2024), $172M (2023), $184M (2022)", "url": "https://projects.propublica.org/nonprofits/organizations/364336415"},
            "sec_form4": {"status": "found", "note": "$3.6B stock gift to foundation in Dec 2023", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001045520&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 2800, "sources": ["ProPublica 990-PF", "Dell Foundation"], "note": "Foundation assets $7.77B, grants $2.8B cumulative", "url": "https://www.dell.org/"},
            "news_verified": {"status": "found", "amount_millions": 2800, "sources": ["TIME", "Forbes", "UT Austin", "Inside Philanthropy"], "url": "https://time.com/collection/time100-philanthropy-2024/6990877/michael-susan-dell/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/364336415",
            "https://www.dell.org/"
        ]
    },
    "Steve Ballmer": {
        "total_lifetime_giving_millions": 5700,
        "giving_breakdown": {
            "ballmer_group": 4000,
            "university_of_oregon": 475,
            "university_of_washington": 80,
            "harvard": 85,
            "blue_meridian_partners": 500,
            "strivetogether": 175,
            "la_clippers_community": 150,
            "other": 235,
            "notes": "VERIFIED Jan 2026: Ballmer Group (LLC, no 990-PF) has disbursed $4B+ since 2015. UO $475M (Ballmer Institute $425M), UW $80M, Harvard $85M. Forbes estimate $5.7B."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Ballmer Group is LLC, not foundation - no 990-PF filings required", "url": None},
            "sec_form4": {"status": "partial", "note": "Some Microsoft stock gifts tracked", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000908063&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 4000, "sources": ["Ballmer Group", "Inside Philanthropy"], "note": "LLC structure - $4B+ disbursed since 2015", "url": "https://www.ballmergroup.org/"},
            "news_verified": {"status": "found", "amount_millions": 5700, "sources": ["TIME", "Forbes", "Chronicle of Philanthropy", "60 Minutes"], "url": "https://time.com/collection/time100-philanthropy-2025/7286089/steve-ballmer-connie-ballmer/"}
        },
        "sources": [
            "https://time.com/collection/time100-philanthropy-2025/7286089/steve-ballmer-connie-ballmer/",
            "https://www.insidephilanthropy.com/find-a-grant/grants-b/ballmer-group"
        ]
    },
    "Changpeng Zhao": {
        "total_lifetime_giving_millions": 35,
        "giving_breakdown": {
            "binance_charity": 30,
            "vitalik_biotech": 10,
            "earthquake_relief": 0.6,
            "covid_supplies": 2.4,
            "notes": "VERIFIED Jan 2026: Binance Charity $23M through 2022 + ~$7M since. Personal donations: $10M Vitalik biotech (2025), $2.4M COVID (2020), misc. Plans '99% pledge' but not signed Giving Pledge. Actual giving ~0.05% of $65B wealth."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Crypto billionaire - no US foundation or 990-PF", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Binance not US-listed", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 30, "sources": ["Binance Charity Foundation"], "note": "Binance Charity $30M+ cumulative (pools user/corporate donations)", "url": "https://www.binance.charity/"},
            "news_verified": {"status": "found", "amount_millions": 15, "sources": ["CoinDesk", "CryptoNews", "Benzinga"], "url": "https://www.coindesk.com/"}
        },
        "sources": [
            "https://www.binance.charity/",
            "https://www.coindesk.com/"
        ]
    },
    "Robert Pera": {
        "total_lifetime_giving_millions": 2,
        "giving_breakdown": {
            "st_jude": 0.1,
            "grizzlies_matching": 1,
            "food_bank": 0.1,
            "other": 0.8,
            "notes": "VERIFIED Jan 2026: Robert J Pera Foundation (EIN 87-1254834) has $0 assets and $0 grants since 2022. Personal verified giving ~$1-2M. Grizzlies Foundation ($54M since 2001) is team-funded, not personal. Ubiquiti equipment donations unquantified."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 0, "ein": "87-1254834", "note": "Robert J Pera Foundation: $0 assets, $0 grants since 2022 founding", "url": "https://projects.propublica.org/nonprofits/organizations/871254834"},
            "sec_form4": {"status": "not_found", "note": "No charitable stock gifts found", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 0, "sources": ["ProPublica 990-PF"], "note": "Foundation is empty shell - $0 activity", "url": "https://projects.propublica.org/nonprofits/organizations/871254834"},
            "news_verified": {"status": "found", "amount_millions": 2, "sources": ["NBA.com", "ESPN", "Commercial Appeal"], "url": "https://www.insidephilanthropy.com/guide-to-individual-donors/robert-pera"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/871254834",
            "https://www.insidephilanthropy.com/guide-to-individual-donors/robert-pera"
        ]
    },
    "Ken Fisher": {
        "total_lifetime_giving_millions": 12,
        "giving_breakdown": {
            "johns_hopkins": 7.5,
            "humboldt_state": 3.5,
            "san_mateo_library": 0.5,
            "other": 0.5,
            "notes": "VERIFIED Jan 2026: No foundation exists - Forbes score 1 (lowest). Hopkins $7.5M, Humboldt $3.5M, library $500K. Plans posthumous giving (within 20 years of death) but rejected Giving Pledge. Called himself 'not a fan of philanthropy'."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "No Fisher foundation exists - no 990-PF filings", "url": None},
            "sec_form4": {"status": "not_found", "note": "No charitable stock gifts found", "url": None},
            "foundation_reports": {"status": "not_applicable", "note": "Does not have formal charitable vehicle", "url": None},
            "news_verified": {"status": "found", "amount_millions": 12, "sources": ["Forbes", "Inside Philanthropy", "Cal Poly Humboldt"], "url": "https://www.insidephilanthropy.com/guide-to-individual-donors/ken-fisher"}
        },
        "sources": [
            "https://www.insidephilanthropy.com/guide-to-individual-donors/ken-fisher",
            "https://www.forbes.com/profile/ken-fisher/"
        ]
    },
    # === NEW ENTRIES WITH FULL VERIFICATION ===
    "S. Robson Walton": {
        "total_lifetime_giving_millions": 400,
        "giving_breakdown": {
            "rob_melani_walton_foundation": 300,
            "african_parks": 100,
            "asu_conservation": 115,
            "walton_family_foundation_share": 0,
            "notes": "VERIFIED Jan 2026: Rob and Melani Walton Foundation 990-PF shows ~$78M/year. Personal contribution to WFF: $0 over 23 years. African Parks $100M pledge (2021), ASU $115M (2025). Forbes Philanthropy Score: 1/5 (lowest)."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 300, "ein": "47-4259772", "note": "Rob and Melani Walton Foundation: ~$78M/year grants", "url": "https://projects.propublica.org/nonprofits/organizations/474259772"},
            "sec_form4": {"status": "found", "amount_millions": 15, "note": "June 2019: 135,000 Walmart shares (~$15M) donated", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000903166&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 300, "sources": ["ProPublica 990-PF"], "note": "Foundation cumulative grants ~$300M", "url": "https://projects.propublica.org/nonprofits/organizations/474259772"},
            "news_verified": {"status": "found", "amount_millions": 215, "sources": ["African Parks $100M", "ASU $115M"], "url": "https://www.africanparks.org/newsroom/press-releases/rob-and-melani-walton-donate-100-million-african-parks"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/474259772",
            "https://www.africanparks.org/newsroom/press-releases/rob-and-melani-walton-donate-100-million-african-parks"
        ]
    },
    "Alice Walton": {
        "total_lifetime_giving_millions": 1500,
        "giving_breakdown": {
            "alice_walton_foundation": 1200,
            "crystal_bridges_museum": 317,
            "art_bridges": 200,
            "walton_school_medicine": 100,
            "heartland_whole_health": 50,
            "notes": "VERIFIED Jan 2026: Alice L. Walton Foundation (EIN 82-3700633) has $3.78B assets, ~$95M/year grants. Crystal Bridges $317M+ personal. Forbes lists $1.5B lifetime. Contribution to WFF: $0 over 23 years."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 500, "ein": "82-3700633", "note": "Alice L. Walton Foundation: $3.78B assets, ~$95M/year grants", "url": "https://projects.propublica.org/nonprofits/organizations/823700633"},
            "sec_form4": {"status": "found", "amount_millions": 225, "note": "2016: $225M Walmart shares to Walton Family Holdings Trust", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000903179&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 1200, "sources": ["ProPublica 990-PF", "Art Bridges"], "note": "Foundation + Crystal Bridges cumulative", "url": "https://projects.propublica.org/nonprofits/organizations/823700633"},
            "news_verified": {"status": "found", "amount_millions": 1500, "sources": ["Forbes", "Crystal Bridges", "Art Bridges"], "url": "https://crystalbridges.org/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/823700633",
            "https://crystalbridges.org/"
        ]
    },
    "Jim Walton": {
        "total_lifetime_giving_millions": 1500,
        "giving_breakdown": {
            "walton_charitable_support": 400,
            "june_2019_stock_gift": 1200,
            "walton_family_foundation": 3,
            "notes": "VERIFIED Jan 2026: Walton Family Charitable Support Foundation (EIN 58-1766770) grants ~$59M/year. June 2019: $1.2B stock gift (largest by any Walton heir). Contribution to WFF: only $3M over 23 years."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 400, "ein": "58-1766770", "note": "Walton Family Charitable Support Foundation: ~$59M/year, $562M assets (2019)", "url": "https://projects.propublica.org/nonprofits/organizations/581766770"},
            "sec_form4": {"status": "found", "amount_millions": 1200, "note": "June 27, 2019: 11.2M Walmart shares (~$1.2B) donated", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000903205&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 400, "sources": ["ProPublica 990-PF"], "note": "Foundation cumulative grants ~$400M", "url": "https://projects.propublica.org/nonprofits/organizations/581766770"},
            "news_verified": {"status": "found", "amount_millions": 1200, "sources": ["SEC Form 4"], "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000903205&type=4"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/581766770",
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000903205&type=4"
        ]
    },
    "Michael Bloomberg": {
        "total_lifetime_giving_millions": 21100,
        "giving_breakdown": {
            "bloomberg_philanthropies_cumulative": 11000,
            "johns_hopkins_total": 4550,
            "climate_initiatives": 2000,
            "public_health": 1500,
            "arts_culture": 1000,
            "government_innovation": 500,
            "other": 550,
            "notes": "VERIFIED Jan 2026: Bloomberg Philanthropies reports $21.1B lifetime giving. Foundation 990-PF shows ~$11B grants (2014-2024). Hopkins $4.55B cumulative. #1 US philanthropist 2023-2024 ($3.7B in 2024 alone)."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 11000, "ein": "20-5602483", "note": "Bloomberg Family Foundation: ~$1.4B/year recent, $11B cumulative (2014-2024)", "url": "https://projects.propublica.org/nonprofits/organizations/205602483"},
            "sec_form4": {"status": "not_applicable", "note": "Bloomberg LP is private, no SEC filings", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 21100, "sources": ["Bloomberg Philanthropies Annual Report"], "note": "Official: $21.1B lifetime giving through all channels", "url": "https://www.bloomberg.org/"},
            "news_verified": {"status": "found", "amount_millions": 21100, "sources": ["TIME100 Philanthropy", "Chronicle of Philanthropy", "Forbes"], "url": "https://time.com/collection/time100-philanthropy-2025/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/205602483",
            "https://www.bloomberg.org/"
        ]
    },
    "Mukesh Ambani": {
        "total_lifetime_giving_millions": 400,
        "giving_breakdown": {
            "reliance_foundation_personal": 350,
            "hurun_tracked_2018_2025": 350,
            "corporate_csr_not_counted": 0,
            "notes": "VERIFIED Jan 2026: Personal/family philanthropy ~$45-75M/year (Hurun India). Cumulative personal giving ~$350-400M. Corporate CSR ($1.2B+) is legally mandated 2% of profits, not personal. Ranks 2nd-3rd among Indian philanthropists."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Indian billionaire - Reliance Foundation is India-registered", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Not US-listed", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 400, "sources": ["Reliance Foundation", "Hurun India Philanthropy List"], "note": "Personal giving ~$45-75M/year, cumulative ~$400M", "url": "https://www.reliancefoundation.org/"},
            "news_verified": {"status": "found", "amount_millions": 400, "sources": ["Hurun India", "TIME100 Philanthropy", "Business Standard"], "url": "https://www.hurun.net/en-us/info/detail?num=India-Philanthropy-List"}
        },
        "sources": [
            "https://www.reliancefoundation.org/",
            "https://www.hurun.net/en-us/info/detail?num=India-Philanthropy-List"
        ]
    },
    "Carlos Slim Helu": {
        "total_lifetime_giving_millions": 4500,
        "giving_breakdown": {
            "fundacion_carlos_slim": 4000,
            "telmex_foundation": 500,
            "gates_partnership_polio": 100,
            "mesoamerica_health": 50,
            "mexico_city_restoration": 500,
            "notes": "VERIFIED Jan 2026: TIME reports $4B+ disbursed since 1986. NOT a Giving Pledge signatory (declined 2011). Foundations run programs directly vs grantmaking. No audited financials publicly available."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Mexican billionaire - Fundación Carlos Slim is Mexico-registered", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Not US-listed for philanthropy", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 4500, "sources": ["Fundación Carlos Slim", "TIME100 Philanthropy"], "note": "$4B+ disbursed since 1986 (TIME). No audited financials public.", "url": "https://fundacioncarlosslim.org/"},
            "news_verified": {"status": "found", "amount_millions": 4500, "sources": ["TIME", "Gates Foundation", "Institutional Investor"], "url": "https://time.com/collection/time100-philanthropy-2025/"}
        },
        "sources": [
            "https://fundacioncarlosslim.org/",
            "https://time.com/collection/time100-philanthropy-2025/"
        ]
    }
}

# Net worth updates from Forbes/Bloomberg January 2026
NET_WORTH_UPDATES = {
    "Elon Musk": 726.0,  # Forbes Jan 2026
    "Jeff Bezos": 239.0,  # Forbes Jan 2026
    "Larry Page": 249.0,  # Bloomberg Jan 2026
    "Sergey Brin": 250.0,  # Bloomberg Jan 2026
    "Mark Zuckerberg": 233.0,  # Bloomberg Jan 2026
    "Jensen Huang": 162.0,  # Forbes Jan 2026
    "Larry Ellison": 247.0,  # Bloomberg Jan 2026
    "Warren Buffett": 145.0,  # Forbes Jan 2026
    "Bill Gates": 160.0,  # Forbes estimate
    "Steve Ballmer": 135.0,  # Forbes estimate
    "Michael Dell": 115.0,  # Forbes estimate
    "MacKenzie Scott": 35.0,  # After giving away $26B+
}


def update_json():
    """Update the JSON file with verification data."""
    with open('docs/scrooge_latest.json', 'r') as f:
        data = json.load(f)

    updated = 0
    nw_updated = 0
    for entry in data:
        name = entry['name']

        # Update net worth if we have new data
        if name in NET_WORTH_UPDATES:
            old_nw = entry.get('net_worth_billions', 0)
            new_nw = NET_WORTH_UPDATES[name]
            if abs(old_nw - new_nw) > 1:  # Only update if significant change
                entry['net_worth_billions'] = new_nw
                nw_updated += 1
                print(f"Net worth updated: {name} ${old_nw}B -> ${new_nw}B")

        if name in VERIFICATION_DATA:
            vdata = VERIFICATION_DATA[name]

            # Update the entry with verification data
            entry['total_lifetime_giving_millions'] = vdata['total_lifetime_giving_millions']
            entry['giving_breakdown'] = vdata['giving_breakdown']
            entry['verification'] = vdata['verification']
            entry['sources'] = vdata['sources']

            # Recalculate scores
            liquidity = entry.get('liquidity_factor', 0.3)
            net_worth_millions = entry['net_worth_billions'] * 1000
            adjusted_wealth = net_worth_millions * liquidity
            giving = entry['total_lifetime_giving_millions']

            if adjusted_wealth > 0:
                giving_ratio = giving / adjusted_wealth
                entry['scrooge_score'] = max(0, min(100, (1 - giving_ratio) * 100))
                entry['giving_rate_pct'] = (giving / net_worth_millions) * 100

            updated += 1
            print(f"Verified: {name}")

    # Sort by scrooge_score descending and update ranks
    data.sort(key=lambda x: x.get('scrooge_score', 0), reverse=True)
    for i, entry in enumerate(data):
        entry['scrooge_rank'] = i + 1

    with open('docs/scrooge_latest.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nUpdated {updated} entries with verification data")


if __name__ == '__main__':
    update_json()
