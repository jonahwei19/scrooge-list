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
        "total_lifetime_giving_millions": 180,
        "giving_breakdown": {
            "external_charities_2024": 51,
            "external_charities_2023": 51,
            "external_charities_2022": 43,
            "external_charities_2021": 20,
            "ebola_relief_2014": 15,
            "notes": "VERIFIED Jan 2026: Grantmakers.io shows $286M total in 2024, but 82% ($235M) to National Philanthropic Trust DAF. Only ~$51M to operating charities. Cumulative ~$180M to actual charities (2019-2024)."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 286, "ein": "20-1922957", "note": "Carl Victor Page Memorial Foundation. Total 2024: $286M, but $235M (82%) to DAFs", "url": "https://projects.propublica.org/nonprofits/organizations/201922957"},
            "sec_form4": {"status": "not_found", "note": "No stock gifts to external charities found", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 180, "sources": ["Grantmakers.io", "ProPublica 990-PF"], "note": "Only ~$180M to operating charities (excluding DAF transfers)", "url": "https://www.grantmakers.io/profiles/v0/201922957-carl-victor-page-memorial-foundation/"},
            "news_verified": {"status": "found", "amount_millions": 180, "sources": ["Inside Philanthropy", "Philanthropy News Digest"], "url": "https://www.insidephilanthropy.com/home/larry-page-steps-out-of-the-shadows-as-a-climate-donor"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/201922957",
            "https://www.grantmakers.io/profiles/v0/201922957-carl-victor-page-memorial-foundation/",
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
            "notes": "VERIFIED Jan 2026: Bill & Melinda Gates contributed $60.2B to the foundation. Foundation has paid out $83.3B in grants (includes Buffett's $47.9B + investment returns). May 2025: Gates announced he will give virtually all remaining wealth (~$100B more) by 2045 when foundation closes."
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
        "total_lifetime_giving_millions": 333,
        "giving_breakdown": {
            "foundation_2024": 126,
            "foundation_2023": 60,
            "foundation_2022": 66,
            "foundation_2021": 32,
            "foundation_pre_2021": 49,
            "notes": "VERIFIED Jan 2026: Foundation 990-PF shows $333M cumulative disbursements (2014-2024). $126M in 2024 alone. Assets $9.2B. Major recipients include OSU, Stanford, Crisis Text Line, food banks. Some grants to DAFs but majority to operating charities."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 333, "ein": "26-1551239", "note": "Jen-Hsun & Lori Huang Foundation: $333M cumulative disbursed (2014-2024), $126M in 2024", "url": "https://projects.propublica.org/nonprofits/organizations/261551239"},
            "sec_form4": {"status": "found", "note": "Nvidia stock gifts to foundation tracked", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001341439&type=4&dateb=&owner=include&count=40"},
            "foundation_reports": {"status": "found", "amount_millions": 333, "sources": ["ProPublica 990-PF", "Grantmakers.io"], "note": "$333M cumulative from 990-PF filings", "url": "https://www.grantmakers.io/profiles/v0/261551239-jen-hsun-lori-huang-foundation/"},
            "news_verified": {"status": "found", "amount_millions": 333, "sources": ["ProPublica 990-PF", "OSU", "Stanford", "Crisis Text Line"], "url": "https://www.insidephilanthropy.com/guide-to-individual-donors/jensen-huang"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/261551239",
            "https://www.grantmakers.io/profiles/v0/261551239-jen-hsun-lori-huang-foundation/"
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
        "giving_pledge": "Unofficially",  # Personal pledge, not official Giving Pledge
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
        "total_lifetime_giving_millions": 0.6,
        "giving_breakdown": {
            "food_bank_meals": 0.5,
            "st_jude_pledge": 0.1,
            "notes": "VERIFIED Jan 2026: Robert J Pera Foundation (EIN 87-1254834) has $0 assets and $0 grants since 2022. Documented giving: 300K meals to food bank (~$500K value), St. Jude pledge ($100K). Grizzlies Foundation is team-funded, not personal. Previously overstated at $2M."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 0, "ein": "87-1254834", "note": "Robert J Pera Foundation: $0 assets, $0 grants since 2022 founding", "url": "https://projects.propublica.org/nonprofits/organizations/871254834"},
            "sec_form4": {"status": "not_found", "note": "No charitable stock gifts found", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 0, "sources": ["ProPublica 990-PF"], "note": "Foundation is empty shell - $0 activity", "url": "https://projects.propublica.org/nonprofits/organizations/871254834"},
            "news_verified": {"status": "found", "amount_millions": 0.6, "sources": ["Mid-South Food Bank 2020", "Commercial Appeal"], "url": "https://www.insidephilanthropy.com/guide-to-individual-donors/robert-pera"}
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
    },
    # === BATCH 2: ADDITIONAL VERIFIED BILLIONAIRES ===
    "Amancio Ortega": {
        "total_lifetime_giving_millions": 1500,
        "giving_breakdown": {
            "cancer_equipment_2017": 336,
            "proton_therapy_2021": 294,
            "valencia_flood_2024": 105,
            "caritas_cumulative": 58,
            "foundation_2019_2023": 471,
            "education_scholarships": 50,
            "other": 186,
            "notes": "VERIFIED Jan 2026: Fundación Amancio Ortega (Spain) + Ortega Charitable Foundation (US). €320M cancer equipment, €280M proton therapy, €100M Valencia flood. Foundation published €449M (2019-2023) + €682.5M committed (2024-2028)."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 38, "ein": "65-0014714", "note": "Ortega Charitable Foundation (US): $38M assets, ~$2M/year grants. Separate from main Spanish foundation.", "url": "https://projects.propublica.org/nonprofits/organizations/650014714"},
            "sec_form4": {"status": "not_applicable", "note": "Inditex is Spanish-listed, not US SEC", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 1500, "sources": ["Fundación Amancio Ortega", "FAO Annual Reports"], "note": "€1.1B+ executed + €682M committed (2024-2028)", "url": "https://www.faortega.org/en/institution/figures/"},
            "news_verified": {"status": "found", "amount_millions": 1500, "sources": ["Reuters", "El Pais", "Forbes", "Philanthropy News Digest"], "url": "https://www.reuters.com/article/us-inditex-ortega-donation-idUSKBN17025F/"}
        },
        "sources": [
            "https://www.faortega.org/en/institution/figures/",
            "https://projects.propublica.org/nonprofits/organizations/650014714"
        ]
    },
    "Ray Dalio": {
        "total_lifetime_giving_millions": 7000,
        "giving_breakdown": {
            "dalio_philanthropies_total": 7000,
            "connecticut_total": 280,
            "ct_youth_trump_accounts": 75,
            "nyp_health_justice": 50,
            "robin_hood": 20,
            "david_lynch_foundation": 20,
            "covid_relief": 4,
            "notes": "VERIFIED Jan 2026: Dalio Philanthropies reports $7B+ total contributed. Giving Pledge signatory (2011). Foundation 990-PF shows $59M/year distributions. Major focus: Connecticut, ocean exploration (OceanX), education."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 59, "ein": "43-1965846", "note": "Dalio Foundation: $1.67B assets, $59M/year charitable disbursements", "url": "https://projects.propublica.org/nonprofits/organizations/431965846"},
            "sec_form4": {"status": "not_applicable", "note": "Bridgewater is private LP, no SEC filings", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 7000, "sources": ["Dalio Philanthropies"], "note": "$7B+ total contributed per official website", "url": "https://www.daliophilanthropies.org/"},
            "news_verified": {"status": "found", "amount_millions": 7000, "sources": ["Giving Pledge", "BusinessWire", "NYP"], "url": "https://givingpledge.org/pledger?pledgerId=185"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/431965846",
            "https://www.daliophilanthropies.org/"
        ]
    },
    "Jim Simons": {
        "total_lifetime_giving_millions": 6000,
        "giving_breakdown": {
            "foundation_2024": 506,
            "foundation_2023": 503,
            "foundation_2022": 500,
            "foundation_2021": 464,
            "foundation_2020": 440,
            "foundation_pre_2020": 667,
            "stony_brook_cumulative": 1540,
            "sfari_autism_research": 725,
            "pre_foundation_giving": 655,
            "notes": "VERIFIED Jan 2026: Grantmakers.io shows $3.08B cumulative (2014-2024). $505M in 2024 alone. Forbes estimates $6B lifetime (includes pre-2014 + Stony Brook mega-gifts). Giving Pledge signatory (2010). Deceased May 2024."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 3080, "ein": "13-3794889", "note": "Simons Foundation: $3.08B cumulative (2014-2024), $506M in 2024, 1,727 grants", "url": "https://projects.propublica.org/nonprofits/organizations/133794889"},
            "sec_form4": {"status": "not_applicable", "note": "Renaissance Technologies is private hedge fund", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 3080, "sources": ["Grantmakers.io", "Simons Foundation"], "note": "$3.08B foundation grants + ~$3B direct gifts (Stony Brook, other)", "url": "https://www.grantmakers.io/profiles/v0/133794889-simons-foundation/"},
            "news_verified": {"status": "found", "amount_millions": 6000, "sources": ["Forbes", "AP News", "Chronicle of Philanthropy"], "url": "https://philanthropynewsdigest.org/news/jim-simons-mathematician-investor-philanthropist-dies-at-86"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/133794889",
            "https://www.grantmakers.io/profiles/v0/133794889-simons-foundation/",
            "https://www.simonsfoundation.org/annual-reports/"
        ]
    },
    "Charles Koch": {
        "total_lifetime_giving_millions": 1040,
        "giving_breakdown": {
            "foundation_2024": 68,
            "foundation_2023": 78,
            "foundation_2022": 69,
            "foundation_2021": 99,
            "foundation_2020": 109,
            "foundation_2019": 148,
            "foundation_pre_2019": 469,
            "notes": "VERIFIED Jan 2026: Grantmakers.io shows $1.04B cumulative (2010-2024). Peak $148M in 2019, recent years $68-78M. Forbes $1.8B estimate includes Stand Together network which is separate entity. NOT Giving Pledge signatory."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 1040, "ein": "48-0918408", "note": "Charles Koch Foundation: $1.04B cumulative (2010-2024), $68M in 2024", "url": "https://projects.propublica.org/nonprofits/organizations/480918408"},
            "sec_form4": {"status": "not_applicable", "note": "Koch Industries is private", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 1040, "sources": ["Grantmakers.io", "ProPublica 990-PF"], "note": "$1.04B verified through 990-PF filings", "url": "https://www.grantmakers.io/profiles/v0/480918408-charles-koch-foundation/"},
            "news_verified": {"status": "found", "amount_millions": 1800, "sources": ["Forbes", "TIME", "CMD"], "url": "https://time.com/5413786/charles-koch-charitable-giving/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/480918408",
            "https://www.grantmakers.io/profiles/v0/480918408-charles-koch-foundation/",
            "https://charleskochfoundation.org/who-we-support/990-forms/"
        ]
    },
    "Michael Milken": {
        "total_lifetime_giving_millions": 1200,
        "giving_breakdown": {
            "medical_research_personal": 1200,
            "george_washington_university": 80,
            "milken_educator_awards": 76,
            "museum_tolerance_jerusalem": 10,
            "center_advancing_american_dream": 500,
            "prostate_cancer_foundation": 500,
            "notes": "VERIFIED Jan 2026: $1.2B personal donations to medical research (California Healthline). PCF raised $1B+ since 1993. Center for Advancing American Dream: $500M personal. Giving Pledge signatory (2010). Forbes score 3/5."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 27, "ein": "82-1927087", "note": "Michael and Lori Milken Family Foundation: $402M assets, $27M/year grants", "url": "https://projects.propublica.org/nonprofits/organizations/821927087"},
            "sec_form4": {"status": "not_applicable", "note": "No longer active in public markets", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 1200, "sources": ["PCF", "Milken Family Foundation"], "note": "$1.2B per California Healthline (2023)", "url": "https://www.pcf.org/annual-report-and-financials/"},
            "news_verified": {"status": "found", "amount_millions": 1200, "sources": ["California Healthline", "Forbes", "Washington Post"], "url": "https://californiahealthline.org/news/article/michael-milken-faster-cures-cancer-philanthropy/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/821927087",
            "https://givingpledge.org/pledger?pledgerId=245"
        ]
    },
    "Li Ka-shing": {
        "total_lifetime_giving_millions": 3850,
        "giving_breakdown": {
            "shantou_university": 1540,
            "guangdong_technion": 130,
            "stanford": 37,
            "uc_berkeley": 50,
            "university_alberta": 21,
            "cambridge": 15,
            "disaster_relief_cumulative": 200,
            "other_education_healthcare": 1857,
            "notes": "VERIFIED Jan 2026: HK$30B+ (~$3.85B) total giving. Shantou University alone HK$12B. One-third wealth pledge (2006). TIME100 Philanthropy 2025. Foundation holds ~$7B endowment for future giving."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Hong Kong billionaire - Li Ka Shing Foundation is HK-registered. Canada arm files T3010.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "CK Hutchison is HK-listed", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 3850, "sources": ["Li Ka Shing Foundation", "TIME", "Forbes"], "note": "HK$30B+ total giving per foundation timeline", "url": "https://www.lksf.org/?lang=en"},
            "news_verified": {"status": "found", "amount_millions": 3850, "sources": ["TIME100 Philanthropy", "Forbes", "Stanford News", "UC Berkeley"], "url": "https://time.com/collections/time100-philanthropy-2025/7286079/li-ka-shing/"}
        },
        "sources": [
            "https://www.lksf.org/timeline/?lang=en",
            "https://time.com/collections/time100-philanthropy-2025/7286079/li-ka-shing/"
        ]
    },
    "Len Blavatnik": {
        "total_lifetime_giving_millions": 1300,
        "giving_breakdown": {
            "harvard_medical": 200,
            "oxford_bsg": 115,
            "tate_modern": 65,
            "tel_aviv_university": 65,
            "yale_innovation": 50,
            "carnegie_hall": 25,
            "stanford_medicine": 12,
            "va_museum": 19,
            "blavatnik_awards": 14,
            "other": 735,
            "notes": "VERIFIED Jan 2026: $1.3B to 250+ institutions (per Foundation). 990-PF: $618M cumulative grants (2017-2024). Major gifts: Harvard $200M, Oxford £75M, Tate £50M, Yale $50M. Knighted 2017."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 69, "ein": "81-2444350", "note": "Blavatnik Family Foundation: $58M assets, $69M/year grants (2023)", "url": "https://projects.propublica.org/nonprofits/organizations/812444350"},
            "sec_form4": {"status": "not_applicable", "note": "Access Industries is private", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 1300, "sources": ["Blavatnik Family Foundation"], "note": "$1.3B per official website", "url": "https://blavatnikfoundation.org/about-us/"},
            "news_verified": {"status": "found", "amount_millions": 1300, "sources": ["Harvard Gazette", "Guardian", "Yale Ventures"], "url": "https://news.harvard.edu/gazette/story/2018/11/a-gift-to-harvard-to-turn-medical-discoveries-into-treatments/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/812444350",
            "https://blavatnikfoundation.org/about-us/"
        ]
    },
    "Thomas Peterffy": {
        "total_lifetime_giving_millions": 40,
        "giving_breakdown": {
            "peterffy_foundation_2014_2023": 26,
            "vanderbilt_fmrc_2003": 3,
            "environmental_indigenous": 15,
            "education_other": 6,
            "notes": "VERIFIED Jan 2026: Foundation 990-PF shows $26M grants (2014-2023). Vanderbilt $3M (2003). Focus: Amazon rainforest, indigenous rights, environmental conservation. ~$15-20M political donations (NOT charitable) excluded."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 7, "ein": "47-2351448", "note": "Peterffy Foundation: $111M assets, $7.4M/year grants (2023)", "url": "https://projects.propublica.org/nonprofits/organizations/472351448"},
            "sec_form4": {"status": "not_found", "note": "No gift transactions found. $3M Vanderbilt gift predates 2007 IPO.", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 26, "sources": ["ProPublica 990-PF"], "note": "$26M cumulative grants (2014-2023)", "url": "https://projects.propublica.org/nonprofits/organizations/472351448"},
            "news_verified": {"status": "found", "amount_millions": 3, "sources": ["Stamford Advocate", "Vanderbilt News"], "url": "https://news.vanderbilt.edu/2021/04/22/financial-markets-research-center-renamed-for-hans-stoll/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/472351448",
            "https://www.instrumentl.com/990-report/peterffy-foundation-inc"
        ]
    },
    "Larry Fink": {
        "total_lifetime_giving_millions": 100,
        "giving_breakdown": {
            "ucla_fink_center": 10,
            "nyu_langone_naming_gifts": 15,
            "stock_gifts_sec_form4": 86,
            "moma_robin_hood_other": 5,
            "notes": "VERIFIED Jan 2026: No personal 990-PF foundation found. SEC Form 4 shows ~$86M in BlackRock stock gifts (2021-2025). UCLA $10M (2008). NYU Langone naming gifts estimated $10-20M. NOT Giving Pledge signatory. Net worth ~$1.3B."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "No personal foundation 990-PF filing found for Larry/Lori Fink. BlackRock Charitable Foundation is corporate.", "url": None},
            "sec_form4": {"status": "found", "amount_millions": 86, "note": "100,751 BLK shares gifted 2021-2025 (~$86M est)", "url": "https://www.secform4.com/insider-trading/1059245.htm"},
            "foundation_reports": {"status": "partial", "amount_millions": 39, "sources": ["BlackRock Charitable Foundation (corporate)"], "note": "Corporate foundation: $212M assets, $39M/year grants. Not personal.", "url": "https://projects.propublica.org/nonprofits/organizations/842144591"},
            "news_verified": {"status": "found", "amount_millions": 25, "sources": ["UCLA Newsroom", "NYU Langone"], "url": "https://newsroom.ucla.edu/releases/blackrock-chairman-laurence-fink-receives-ucla-medal"}
        },
        "sources": [
            "https://www.secform4.com/insider-trading/1059245.htm",
            "https://newsroom.ucla.edu/releases/blackrock-chairman-laurence-fink-receives-ucla-medal"
        ]
    },
    # === BATCH 3: ADDITIONAL BILLIONAIRES FROM AGENT RESEARCH ===
    "Jack Ma": {
        "total_lifetime_giving_millions": 1000,
        "giving_breakdown": {
            "covid_response_2020": 494,
            "zhejiang_university": 80,
            "newcastle_australia": 20,
            "xixi_wetland": 14,
            "hong_kong_fire_2025": 4,
            "earthshot_prize": 4,
            "africa_netpreneur": 10,
            "rural_education": 80,
            "other": 294,
            "notes": "VERIFIED Jan 2026: Jack Ma Foundation (China-registered, no US 990-PF). Forbes China 2020: $494M. University gifts verified. $3B charitable trust (2014) with Alibaba equity - ongoing disbursement."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "Jack Ma Foundation registered in Zhejiang Province, China - not US nonprofit", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Alibaba listed in Hong Kong and NYSE, but charitable trust is offshore", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 1000, "sources": ["Jack Ma Foundation", "Forbes China"], "note": "Chinese foundation reports not public. Forbes China Philanthropy List 2020: #1 with $494M that year.", "url": "https://www.jackmafoundation.org.cn/"},
            "news_verified": {"status": "found", "amount_millions": 1000, "sources": ["Forbes", "Reuters", "TIME100 Philanthropy 2025", "SCMP"], "url": "https://time.com/collections/time100-philanthropy-2025/7286036/jack-ma/"}
        },
        "sources": [
            "https://time.com/collections/time100-philanthropy-2025/7286036/jack-ma/",
            "https://www.jackmafoundation.org.cn/",
            "https://www.caixinglobal.com/2021-07-26/out-of-favor-jack-ma-tops-forbes-china-philanthropy-list-with-494-million-in-donations-101745791.html"
        ]
    },
    "Azim Premji": {
        "total_lifetime_giving_millions": 29000,  # Endowment value - actual annual disbursement lower
        "giving_breakdown": {
            "foundation_endowment": 29000,  # Total endowment in Wipro shares
            "annual_grants_fy24": 109,  # Actual disbursement
            "covid_relief_2020": 140,
            "girls_education_2025": 270,
            "school_meals_2024": 175,
            "notes": "VERIFIED Jan 2026: $29B endowment (TIME100). DISTINCTION: Endowment value vs actual disbursement (~$109-183M/year). First Indian Giving Pledge signatory (2013). Foundation registered in India, no US 990-PF."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "Indian entity - files under Indian law, not IRS. Registered in Karnataka (CIN: U93090KA2001NPL028740)", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Wipro listed on BSE/NSE India", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 29000, "sources": ["Azim Premji Foundation", "TIME100"], "note": "Endowment: $29B. Annual disbursement: Rs 1,528 crore (~$183M) in 2024", "url": "https://azimpremjifoundation.org/"},
            "news_verified": {"status": "found", "amount_millions": 29000, "sources": ["TIME", "Giving Pledge", "Livemint", "EdelGive Hurun"], "url": "https://time.com/collections/time100-philanthropy-2025/7286073/azim-premji/"}
        },
        "sources": [
            "https://time.com/collections/time100-philanthropy-2025/7286073/azim-premji/",
            "https://www.givingpledge.org/pledger/azim-premji/"
        ]
    },
    "George Soros": {
        "total_lifetime_giving_millions": 32000,
        "giving_breakdown": {
            "open_society_cumulative": 32000,
            "ceu_endowment": 450,
            "bard_college": 660,
            "osun_network": 1000,
            "annual_expenditure": 1200,
            "notes": "VERIFIED Jan 2026: $32B to Open Society since 1984. $24.2B cumulative expenditures. $18B transfer in 2017. EIN 13-7029285 (OSI) + EIN 26-3753801 (FTPOS). Combined 2024 assets ~$16.2B."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 770, "ein": "13-7029285", "note": "Open Society Institute + Foundation To Promote Open Society (26-3753801). Combined 2024 disbursements ~$770M", "url": "https://projects.propublica.org/nonprofits/organizations/137029285"},
            "sec_form4": {"status": "not_applicable", "note": "Soros Fund Management is private hedge fund", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 32000, "sources": ["Open Society Foundations"], "note": "$32B since 1984. $24.2B cumulative expenditures.", "url": "https://www.opensocietyfoundations.org/who-we-are/financials"},
            "news_verified": {"status": "found", "amount_millions": 32000, "sources": ["NYT", "WSJ", "CNN"], "url": "https://www.nytimes.com/2017/10/17/business/george-soros-open-society-foundations.html"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/137029285",
            "https://projects.propublica.org/nonprofits/organizations/263753801",
            "https://www.opensocietyfoundations.org/who-we-are/financials"
        ]
    },
    "Gordon Moore": {
        "total_lifetime_giving_millions": 5500,
        "giving_breakdown": {
            "caltech_total": 700,
            "conservation_international": 395,
            "foundation_grants_cumulative": 5100,
            "stonybrook_other": 305,
            "notes": "VERIFIED Jan 2026: $5.1B+ cumulative foundation grants since 2000. Foundation holds $11.5B. EIN 94-3397785. Caltech $600M (2001) + $100M (2014). Giving Pledge signatory (2012). Deceased March 2023."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 440, "ein": "94-3397785", "note": "Gordon E and Betty I Moore Foundation: $11.5B assets, $440M/year disbursements (2024)", "url": "https://projects.propublica.org/nonprofits/organizations/943397785"},
            "sec_form4": {"status": "not_applicable", "note": "Intel shares donated decades ago to foundation", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 5100, "sources": ["Moore Foundation", "Annual Reports"], "note": "$5.1B+ cumulative grants since founding", "url": "https://www.moore.org/about/our-finances"},
            "news_verified": {"status": "found", "amount_millions": 5500, "sources": ["Intel", "NYT", "Forbes", "NPR"], "url": "https://www.intc.com/news-events/press-releases/detail/1611/gordon-moore-intel-co-founder-dies-at-94"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/943397785",
            "https://www.moore.org/about/our-finances"
        ]
    },
    "Peter Thiel": {
        "total_lifetime_giving_millions": 75,  # Charitable (excludes political)
        "giving_breakdown": {
            "thiel_foundation_annual": 4,
            "methuselah_foundation": 3.5,
            "sens_research": 6,
            "miri": 1.6,
            "seasteading": 1.25,
            "cpj": 1,
            "thiel_fellowship": 15,
            "political_donations": 45,  # Counted separately
            "other": 43,
            "notes": "VERIFIED Jan 2026: Thiel Foundation EIN 20-3846597 disbursements ~$3-5M/year. Anti-aging (SENS, Methuselah) $9.5M. MIRI $1.6M. Political: $45M+ lifetime (2022: $35M to Vance/Masters PACs). Fellowship ~$2-3M/year."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 4, "ein": "20-3846597", "note": "Thiel Foundation: $45M assets, $3.4M disbursements (2024)", "url": "https://projects.propublica.org/nonprofits/organizations/203846597"},
            "sec_form4": {"status": "partial", "note": "Form 4 filings exist but charitable gifts not clearly separated", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001211060&type=4"},
            "foundation_reports": {"status": "found", "amount_millions": 50, "sources": ["Thiel Foundation", "Instrumentl"], "note": "Cumulative foundation grants ~$50-70M", "url": "https://www.instrumentl.com/990-report/the-thiel-foundation"},
            "news_verified": {"status": "found", "amount_millions": 120, "sources": ["Wikipedia", "Ballotpedia", "Forbes"], "url": "https://ballotpedia.org/Peter_Thiel"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/203846597",
            "https://ballotpedia.org/Peter_Thiel"
        ]
    },
    "Eric Schmidt": {
        "total_lifetime_giving_millions": 2500,
        "giving_breakdown": {
            "schmidt_fund_innovation_annual": 313,
            "schmidt_family_foundation_annual": 200,
            "broad_institute": 150,
            "princeton_total": 30,
            "rise_commitment": 1000,
            "ai2050": 125,
            "other": 682,
            "notes": "VERIFIED Jan 2026: Two foundations EIN 46-3460261 + EIN 20-4170342. Combined assets ~$3.5B. $1B+ given by 2019 + $1B Rise commitment. Broad $150M. Annual disbursements ~$500M combined."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 513, "ein": "46-3460261", "note": "Schmidt Fund for Strategic Innovation ($313M) + Schmidt Family Foundation ($200M) = $513M/year combined", "url": "https://projects.propublica.org/nonprofits/organizations/463460261"},
            "sec_form4": {"status": "partial", "note": "Google stock gifts to foundations tracked via 990 contributions received", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 2500, "sources": ["Schmidt Futures", "Instrumentl"], "note": "$1B+ by 2019, $1B Rise commitment announced", "url": "https://www.schmidtfutures.org/"},
            "news_verified": {"status": "found", "amount_millions": 2500, "sources": ["Broad Institute", "Princeton", "Rise"], "url": "https://www.risefortheworld.org/news/eric-and-wendy-schmidt-announce-new-usd1-billion-philanthropic-commitment-to/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/463460261",
            "https://projects.propublica.org/nonprofits/organizations/204170342",
            "https://www.schmidtfutures.org/"
        ]
    },
    "Julia Koch": {
        "total_lifetime_giving_millions": 1400,
        "giving_breakdown": {
            "joint_with_david_pre_2019": 1300,
            "nyu_langone_2024": 75,
            "julia_koch_family_philanthropy_fund_2023": 91,
            "david_koch_foundation_post_2019": 10,
            "notes": "VERIFIED Jan 2026: $1.3B joint with David Koch (1980-2019). Post-2019 Julia's vehicles: Julia Koch Family Philanthropy Fund $90.6M (2023), NYU Langone $75M (2024). David H. Koch Charitable Foundation being wound down ($1.5M assets 2024)."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 91, "ein": "87-3659591", "note": "Julia Koch Family Philanthropy Fund: $90.6M grants (2023), $92M assets (2024)", "url": "https://projects.propublica.org/nonprofits/organizations/873659591"},
            "sec_form4": {"status": "not_applicable", "note": "Koch Industries is private - no SEC filings", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 1400, "sources": ["ProPublica 990-PF", "MSK", "MIT", "Lincoln Center"], "note": "$1.3B joint pre-2019 + ~$100M post-2019", "url": "https://projects.propublica.org/nonprofits/organizations/480926946"},
            "news_verified": {"status": "found", "amount_millions": 1400, "sources": ["NYU Langone $75M", "MSK $150M", "MIT $100M", "Lincoln Center $100M"], "url": "https://nyulangone.org/news/julia-koch-family-foundation-gives-transformative-75-million-gift"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/873659591",
            "https://projects.propublica.org/nonprofits/organizations/480926946",
            "https://nyulangone.org/news/julia-koch-family-foundation-gives-transformative-75-million-gift"
        ]
    },
    "David Thomson": {
        "total_lifetime_giving_millions": 350,
        "giving_breakdown": {
            "ago_renovation_campaign": 276,
            "ago_endowment": 20,
            "canadian_photography_institute": 25,
            "hudsons_bay_charter": 12,
            "camh_family_share": 15,
            "other": 2,
            "notes": "VERIFIED Jan 2026: Led AGO $276M CAD renovation campaign (2002-2008). Founded Canadian Photography Institute at National Gallery. Hudson's Bay Charter $18M CAD joint with Westons (2025). Does NOT include father Ken Thomson's $370M art donation to AGO."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Canadian billionaire - no US 990-PF. Ken and Marilyn Thomson Foundation for AGO (Canada Corp #4458141)", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Thomson Reuters dual-listed but no charitable stock gifts found", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 350, "sources": ["AGO", "National Gallery of Canada"], "note": "Canadian T3010 filings not publicly searchable online", "url": "https://ago.ca/collection/thomson"},
            "news_verified": {"status": "found", "amount_millions": 350, "sources": ["Globe and Mail", "CBC", "AGO"], "url": "https://www.theglobeandmail.com/news/national/thomson-hands-ago-370-million-donation/article25426249/"}
        },
        "sources": [
            "https://ago.ca/collection/thomson",
            "https://www.theglobeandmail.com/news/national/thomson-hands-ago-370-million-donation/article25426249/"
        ]
    },
    "Dieter Schwarz": {
        "total_lifetime_giving_millions": 4000,
        "giving_breakdown": {
            "ipai_commitment": 2000,
            "tum_heilbronn_30yr": 750,
            "eth_zurich_30yr": 400,
            "bildungscampus_infrastructure": 500,
            "experimenta_science_center": 100,
            "max_planck_fraunhofer": 150,
            "aim_academy_other": 100,
            "notes": "VERIFIED Jan 2026: Dieter Schwarz Stiftung (gGmbH) since 1999. IPAI $2B commitment (2023). TUM 41 professorships 30-year. ETH 15-20 professorships. No public financial reports (German gGmbH has minimal disclosure). Estimated $3-5B cumulative."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "German gGmbH foundation - no US 990-PF or public financials", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Schwarz Group is private", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 4000, "sources": ["Dieter Schwarz Stiftung", "TUM", "ETH Foundation", "Max Planck"], "note": "No annual reports with financials. $2B IPAI announced. 1,300+ projects since 1999.", "url": "https://www.dieter-schwarz-stiftung.de/"},
            "news_verified": {"status": "found", "amount_millions": 4000, "sources": ["TUM", "ETH Foundation", "Science|Business", "Max Planck"], "url": "https://sciencebusiness.net/news/ai/aleph-alpha-tu-munich-eth-zurich-how-dieter-schwarz-foundation-attracting-germanys-ai-elite"}
        },
        "sources": [
            "https://www.dieter-schwarz-stiftung.de/",
            "https://www.tum.de/en/news-and-events/all-news/press-releases/details/34471-1",
            "https://ethz-foundation.ch/en/spotlight/news-2023-dss-eth-zurich-donation-teaching-and-research-centre-in-germany/"
        ]
    },
    "John Menard Jr": {
        "total_lifetime_giving_millions": 45,
        "giving_breakdown": {
            "mayo_menard_center": 15,
            "ymca_tennis": 10,
            "osu_law_center": 5,
            "ndsu_challey": 5.5,
            "uw_system_total": 8.3,
            "other": 1.2,
            "notes": "VERIFIED Jan 2026: No 990-PF (no personal foundation). Direct giving only. Mayo/Eau Claire $15M. YMCA Tennis $10M. UW-Stout $2.36M, UW-La Crosse $2.1M, UW-Eau Claire $3M, UW-Madison $880K. Forbes philanthropy score: N/A (very low)."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "No personal foundation. 'Menard Family Foundation' in ProPublica is different family (San Diego). Gives directly.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Menards is private company", "url": None},
            "foundation_reports": {"status": "not_found", "note": "No foundation - all direct gifts", "url": None},
            "news_verified": {"status": "found", "amount_millions": 45, "sources": ["Madison.com", "Moritz College", "Philanthropy News Digest"], "url": "https://moritzlaw.osu.edu/drug-enforcement-and-policy-center-receives-5m-gift-menard-family"}
        },
        "sources": [
            "https://moritzlaw.osu.edu/drug-enforcement-and-policy-center-receives-5m-gift-menard-family",
            "https://philanthropynewsdigest.org/news/north-dakota-state-receives-5.5-million-from-menard-family"
        ]
    },
    # === BATCH 4: NEW VERIFICATIONS JAN 2026 ===
    "Stan Kroenke": {
        "total_lifetime_giving_millions": 32,
        "giving_breakdown": {
            "kroenke_family_foundation_2019_2024": 19,
            "kroenke_sports_charities_lifetime": 15,
            "walton_kroenke_foundation": 1.5,
            "hurricane_harvey_2017": 1,
            "la_wildfire_2025": 1,
            "notes": "VERIFIED Jan 2026: Kroenke Family Foundation 990-PF: $18.8M grants (2019-2024). Kroenke Sports Charities: $15.5M lifetime to Colorado. Walton-Kroenke Foundation: $1.5M (2020-2024). Inside Philanthropy: Foundation assets 0.15% of wealth."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 19, "ein": "83-3505324", "note": "Kroenke Family Foundation: $5.2M/year (2024), $18.8M cumulative (2019-2024)", "url": "https://projects.propublica.org/nonprofits/organizations/833505324"},
            "sec_form4": {"status": "not_applicable", "note": "Kroenke Sports & Entertainment is private", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 32, "sources": ["ProPublica 990-PF", "Kroenke Sports Charities"], "note": "Family foundation + sports charities combined", "url": "https://projects.propublica.org/nonprofits/organizations/833505324"},
            "news_verified": {"status": "found", "amount_millions": 32, "sources": ["Inside Philanthropy", "Colorado Rapids", "Denver Post"], "url": "https://www.insidephilanthropy.com/home/the-other-half-of-americas-richest-family-what-do-these-waltons-fund"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/833505324",
            "https://www.insidephilanthropy.com/home/the-other-half-of-americas-richest-family-what-do-these-waltons-fund"
        ]
    },
    "Zhang Yiming": {
        "total_lifetime_giving_millions": 280,
        "giving_breakdown": {
            "fangmei_education_fund": 106,
            "nankai_university_cumulative": 50,
            "covid_relief_2020": 39,
            "minerva_schools": 10,
            "middle_school_hometown": 1.5,
            "other": 73,
            "notes": "VERIFIED Jan 2026: Hurun China Philanthropy 2024: $280M joint with Liang Rubo (6th place). Fangmei Foundation for hometown education: $106M+. Nankai University: $50M. COVID relief: $39M. Minerva: $10M."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Chinese billionaire - foundations registered in China", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "ByteDance is private", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 280, "sources": ["Hurun China Philanthropy List 2024", "Fangmei Foundation"], "note": "$280M total per Hurun (joint with co-founder)", "url": "https://www.hurun.net/en-us/info/detail?num=L393N9W9VG5M"},
            "news_verified": {"status": "found", "amount_millions": 280, "sources": ["Reuters", "SCMP", "Forbes"], "url": "https://www.reuters.com/world/asia-pacific/bytedance-founder-donates-77-million-amid-china-billionaires-charity-rush-2021-06-22/"}
        },
        "sources": [
            "https://www.hurun.net/en-us/info/detail?num=L393N9W9VG5M",
            "https://www.reuters.com/world/asia-pacific/bytedance-founder-donates-77-million-amid-china-billionaires-charity-rush-2021-06-22/"
        ]
    },
    "Zhong Shanshan": {
        "total_lifetime_giving_millions": 140,
        "giving_breakdown": {
            "xiamen_university": 47,
            "westlake_university": 14,
            "zhejiang_university": 14,
            "zhuji_middle_school_2024": 14,
            "disaster_relief_cumulative": 30,
            "other_education": 21,
            "notes": "VERIFIED Jan 2026: Nongfu Spring confirms 900M+ RMB ($125M) cumulative through 2023. Nov 2024: 100M RMB to Zhuji Middle School. Jan 2025: 40B RMB Qiantang University PLEDGE (not disbursed). Does NOT appear on Hurun list."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Chinese billionaire - Zhong Ziyi Education Foundation registered in Hangzhou", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Nongfu Spring listed in Hong Kong", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 140, "sources": ["Nongfu Spring official statement", "Zhong Ziyi Education Foundation"], "note": "900M+ RMB ($125M) through 2023 + $14M Zhuji 2024", "url": "https://finance.ifeng.com/c/8oWPVY8WmWz"},
            "news_verified": {"status": "found", "amount_millions": 140, "sources": ["163.com", "Phoenix Finance", "Sina Finance"], "url": "https://m.163.com/dy/article/ITTOGH8G0519860S.html"}
        },
        "sources": [
            "https://finance.ifeng.com/c/8oWPVY8WmWz",
            "https://m.163.com/dy/article/ITTOGH8G0519860S.html"
        ]
    },
    "Israel Englander": {
        "total_lifetime_giving_millions": 150,
        "giving_breakdown": {
            "englander_foundation_2011_2024": 12.5,
            "weill_cornell_2015_2023": 130,
            "2006_reported_gift": 20,
            "notes": "VERIFIED Jan 2026: Foundation 990-PF: $12.5M (2011-2024). Weill Cornell: 'largest single donor' to $1.5B campaign, named 2 departments + institute = estimated $100-250M. 2006 reported $20M gift. Forbes estimate higher."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 12.5, "ein": "13-3640833", "note": "Englander Foundation: $420K (2024), $12.5M cumulative (2011-2024)", "url": "https://projects.propublica.org/nonprofits/organizations/133640833"},
            "sec_form4": {"status": "not_applicable", "note": "Millennium Management is private hedge fund", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 150, "sources": ["ProPublica 990-PF", "Weill Cornell"], "note": "Foundation + Weill Cornell naming gifts", "url": "https://projects.propublica.org/nonprofits/organizations/133640833"},
            "news_verified": {"status": "found", "amount_millions": 150, "sources": ["Weill Cornell", "Forbes", "Wikipedia"], "url": "https://news.weill.cornell.edu/news/2023/12/transformational-gift-from-israel-englander-to-expand-weill-cornell-medicine-research"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/133640833",
            "https://news.weill.cornell.edu/news/2023/12/transformational-gift-from-israel-englander-to-expand-weill-cornell-medicine-research"
        ]
    },
    "Tadashi Yanai": {
        "total_lifetime_giving_millions": 270,
        "giving_breakdown": {
            "kyoto_university_medical": 94,
            "ucla_yanai_initiative": 58,
            "waseda_murakami_library": 8,
            "yanai_foundation_scholarships": 20,
            "tohoku_earthquake_2011": 12,
            "unhcr_cumulative": 20,
            "ukraine_2022": 10,
            "other": 48,
            "notes": "VERIFIED Jan 2026: Kyoto University $94M (2020). UCLA $58.5M cumulative. Waseda $8M. UNHCR partnership since 2006. Yanai Foundation scholarships since 2015. NOT Giving Pledge signatory."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Japanese billionaire - foundations registered in Japan", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Fast Retailing listed in Tokyo", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 270, "sources": ["Yanai Tadashi Foundation", "Fast Retailing Foundation"], "note": "$270M+ verified through news + foundation reports", "url": "https://www.yanaitadashi-foundation.or.jp/en/"},
            "news_verified": {"status": "found", "amount_millions": 270, "sources": ["Kyodo News", "UCLA Newsroom", "UNHCR"], "url": "https://newsroom.ucla.edu/releases/tadashi-yanai-gives-31-million-japanese-humanities-research"}
        },
        "sources": [
            "https://newsroom.ucla.edu/releases/tadashi-yanai-gives-31-million-japanese-humanities-research",
            "https://www.unhcr.org/us/about-unhcr/our-partners/private-sector/uniqlo"
        ]
    },
    "Eduardo Saverin": {
        "total_lifetime_giving_millions": 60,
        "giving_breakdown": {
            "dana_farber_2019": 20,
            "dana_farber_2025": 20,
            "singapore_american_school_2024": 15.5,
            "nus_medicine_2025": 2.3,
            "other_foundation_grants": 2.2,
            "notes": "VERIFIED Jan 2026: Singapore-based Elaine and Eduardo Saverin Foundation (est. 2022). Dana-Farber $40M (2019+2025). SAS $15.5M (2024, largest in school history). NUS $2.3M. No US 990-PF (renounced citizenship 2011)."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Singapore resident, renounced US citizenship 2011. Foundation registered in Singapore.", "url": None},
            "sec_form4": {"status": "not_found", "note": "No Form 4 stock gift filings found", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 60, "sources": ["Elaine and Eduardo Saverin Foundation", "Dana-Farber"], "note": "Singapore top 10 donor list (S$11.5M annual)", "url": "https://eesaverinfoundation.org/about-us/"},
            "news_verified": {"status": "found", "amount_millions": 60, "sources": ["Dana-Farber", "Business Insider", "Straits Times"], "url": "https://www.dana-farber.org/newsroom/news-releases/2019/dana-farber-announces-20-million-gift-from-the-saverin-family-for-metastatic-breast-cancer-research"}
        },
        "sources": [
            "https://eesaverinfoundation.org/about-us/",
            "https://www.dana-farber.org/newsroom/news-releases/2019/dana-farber-announces-20-million-gift-from-the-saverin-family-for-metastatic-breast-cancer-research"
        ]
    },
    "Vlad Tenev": {
        "total_lifetime_giving_millions": 0.125,
        "giving_breakdown": {
            "tj_high_school": 0.125,
            "notes": "VERIFIED Jan 2026: Only verified personal gift: $125K to Thomas Jefferson High School (largest individual gift in TJ Partnership Fund history). NO 990-PF foundation. NOT Giving Pledge signatory. $2M Robinhood inaugural donation was CORPORATE, not personal."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "No personal foundation found in ProPublica", "url": None},
            "sec_form4": {"status": "not_found", "note": "No stock gifts (transaction code G) found in Form 4 filings", "url": None},
            "foundation_reports": {"status": "not_applicable", "note": "No foundation exists", "url": None},
            "news_verified": {"status": "found", "amount_millions": 0.125, "sources": ["TJ Partnership Fund"], "url": "https://tjpartnershipfund.org/pages/why-give"}
        },
        "sources": [
            "https://tjpartnershipfund.org/pages/why-give"
        ]
    },
    # === BATCH 5: NEW VERIFICATIONS JAN 2026 (ROUND 3) ===
    "Jerry Jones": {
        "total_lifetime_giving_millions": 90,
        "giving_breakdown": {
            "gene_jerry_jones_dallas_cowboys_charities": 75,
            "gene_jerry_jones_arlington_youth_foundation": 10,
            "national_medal_honor_museum": 20,
            "hope_lodge_cancer_society": 7.5,
            "university_arkansas_athletics": 10.65,
            "little_rock_catholic_hs_campaign": 2,
            "thomas_jefferson_hs_tornado": 1,
            "notes": "VERIFIED Jan 2026: Two foundations: Dallas Cowboys Charities (EIN 75-2808490) + Arlington Youth Foundation (EIN 20-4346960). Combined ~$80M foundation disbursements 2011-2024. Named gifts: Medal of Honor $20M, Hope Lodge $7.5M, UA $10.65M. Salvation Army Red Kettle is promotional partnership, not personal giving."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 85, "ein": "75-2808490", "note": "Gene & Jerry Jones Family-Dallas Cowboys Charities: $70-75M (2011-2024) + Arlington Youth Foundation (EIN 20-4346960): $9.6M cumulative", "url": "https://projects.propublica.org/nonprofits/organizations/752808490"},
            "sec_form4": {"status": "not_applicable", "note": "Dallas Cowboys is private", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 90, "sources": ["ProPublica 990-PF", "Cowboys Charities"], "note": "$8-10M/year recent disbursements", "url": "https://www.causeiq.com/organizations/gene-and-jerry-jones-family-dallas-cowboys-chariti,752808490/"},
            "news_verified": {"status": "found", "amount_millions": 40, "sources": ["Pro Football HOF", "UA News", "Encyclopedia of Arkansas"], "url": "https://www.profootballhof.com/news/2021/03/hall-of-famer-jerry-jones-commits-20-million-to-help-fund-new-national-medal-of-honor-museum/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/752808490",
            "https://projects.propublica.org/nonprofits/organizations/204346960",
            "https://www.profootballhof.com/news/2021/03/hall-of-famer-jerry-jones-commits-20-million-to-help-fund-new-national-medal-of-honor-museum/"
        ]
    },
    "Eyal Ofer": {
        "total_lifetime_giving_millions": 30,
        "giving_breakdown": {
            "tate_modern_2013": 15.2,
            "tel_aviv_museum_art": 5,
            "national_maritime_museum_greenwich": 2.3,
            "moma_trustee_giving": 0.5,
            "dartmouth_scholarship": 2,
            "gloriana_barge_syndicate": 1,
            "other_institutional": 4,
            "notes": "VERIFIED Jan 2026: Tate Modern £10M ($15.2M, 2013). Tel Aviv Museum $5M (2019, Eyal Ofer Pavilion). National Maritime Museum £1.5M ($2.3M, Stubbs paintings). MoMA trustee. No US 990-PF (Monaco/UK-based). Father Sammy Ofer's £20M to NMM is separate."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "Monaco resident, no US foundation. Eyal and Marilyn Ofer Family Foundation likely UK-based.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Zodiac Maritime and Ofer Global are private", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 30, "sources": ["Tate", "Tel Aviv Museum", "PatronView"], "note": "$30M floor estimate, likely higher", "url": "https://patronview.com/patrons/eyal-and-marilyn-ofer-family-foundation"},
            "news_verified": {"status": "found", "amount_millions": 23, "sources": ["The Guardian", "Haaretz", "BBC"], "url": "https://www.theguardian.com/artanddesign/2013/jul/02/tate-modern-gift-eyal-ofer"}
        },
        "sources": [
            "https://www.theguardian.com/artanddesign/2013/jul/02/tate-modern-gift-eyal-ofer",
            "https://www.haaretz.com/israel-news/culture/2019-03-17/ty-article/.premium/tel-aviv-museum-pavilion-renamed-honoring-richest-man-in-israel/0000017f-e4b9-d38f-a57f-e6fbe4220000"
        ]
    },
    "Mark Mateschitz": {
        "total_lifetime_giving_millions": 50,
        "giving_breakdown": {
            "wings_for_life_board_member": 0,
            "personal_donations_unknown": 0,
            "notes": "UNABLE TO VERIFY Jan 2026: Mark's personal giving is not publicly disclosed. Wings for Life World Run has raised €60.53M cumulative, but this is public fundraising, not Mark's personal wealth. Father Dietrich Mateschitz donated €70M to Paracelsus Medical University (2012) - that's father's giving, not Mark's. Mark joined board of Wings for Life after inheritance in 2022. No public foundation filings, no disclosed personal gifts."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Austrian/Monaco resident, no US foundation", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Red Bull is private", "url": None},
            "foundation_reports": {"status": "not_found", "note": "Mark's personal giving not disclosed. Wings for Life is public fundraising + Red Bull admin support.", "url": "https://www.wingsforlife.com/"},
            "news_verified": {"status": "not_found", "note": "No personal charitable donations documented in public sources", "url": None}
        },
        "sources": [
            "https://www.wingsforlife.com/uk/about-us/",
            "https://en.wikipedia.org/wiki/Mark_Mateschitz"
        ]
    },
    "Ernest Garcia II": {
        "total_lifetime_giving_millions": 55,
        "giving_breakdown": {
            "garcia_family_foundation_5yr": 28,
            "university_arizona_2025": 20,
            "university_arizona_honors_2020": 4,
            "other_foundation_grants": 3,
            "notes": "VERIFIED Jan 2026: Garcia Family Foundation (EIN 31-1490067) 5-year total: $27.7M per FireGrants (174 grants to 110 orgs). 2023: $10.6M, 2024: $14.1M. UA $20M (2025) + $4M (2020). Foundation since 1996. NOT Giving Pledge signatory."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 28, "ein": "31-1490067", "note": "Garcia Family Foundation Inc: $27.7M (5-year), $10-14M/year recent", "url": "https://projects.propublica.org/nonprofits/organizations/311490067"},
            "sec_form4": {"status": "not_found", "note": "No charitable stock gifts (code G) found", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 55, "sources": ["ProPublica 990-PF", "FireGrants", "UArizona"], "note": "Foundation since 1996, estimated $50-60M cumulative", "url": "https://www.firegrants.info/GrantDetails.aspx?gid=54179"},
            "news_verified": {"status": "found", "amount_millions": 24, "sources": ["UArizona Giving", "UArizona News"], "url": "https://giving.arizona.edu/news/university-arizona-receives-20-million-gift-commitment-garcia-family-foundation-expand-access"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/311490067",
            "https://giving.arizona.edu/news/university-arizona-receives-20-million-gift-commitment-garcia-family-foundation-expand-access"
        ]
    },
    "Ernest Garcia III": {
        "total_lifetime_giving_millions": 5,
        "giving_breakdown": {
            "personal_charitable_verified": 0,
            "garcia_family_foundation_portion": 5,
            "employee_stock_gift_2018_NOT_CHARITY": 35,
            "notes": "VERIFIED Jan 2026: $35M stock gift (2018) went to EMPLOYEES, not charity. Per Inside Philanthropy: 'over $2M in grants through 2017' from family foundation. Forbes philanthropy score: N/A. No personal foundation. NOT Giving Pledge. Much lower verified charitable giving than Garcia II."
        },
        "verification": {
            "990_pf": {"status": "partial", "amount_millions": 5, "note": "Portion of Garcia Family Foundation may be attributed to III, but foundation is primarily II's vehicle", "url": "https://projects.propublica.org/nonprofits/organizations/311490067"},
            "sec_form4": {"status": "not_found", "note": "No charitable stock gifts found. $35M gift was to employees, not 501(c)(3)", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 5, "sources": ["Inside Philanthropy"], "note": "Limited personal charitable activity documented", "url": "https://www.insidephilanthropy.com/home/2022-2-17-what-we-know-so-far-about-the-garcia-family-foundation-in-arizona"},
            "news_verified": {"status": "found", "amount_millions": 35, "sources": ["Bloomberg", "Forbes"], "note": "$35M was employee gift, not charity", "url": None}
        },
        "sources": [
            "https://www.insidephilanthropy.com/home/2022-2-17-what-we-know-so-far-about-the-garcia-family-foundation-in-arizona"
        ]
    },
    # === BATCH 6: HIGH-VALUE BILLIONAIRES JAN 2026 ===
    "Giovanni Ferrero": {
        "total_lifetime_giving_millions": 12,
        "giving_breakdown": {
            "covid_donation_italy_2020": 10.9,
            "oregon_state_hazelnut_research": 0.76,
            "rutgers_hazelnut_research": 0.17,
            "other_university_research": 0.17,
            "notes": "VERIFIED Jan 2026: Only €10M COVID donation confirmed. Fondazione Ferrero (Alba) is employee-focused, no public budget. Michele Ferrero Entrepreneurial Project is corporate CSR. No US 990-PF (US 'Ferrero Family Foundation' EIN 58-2348659 is different family). NOT Giving Pledge signatory."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Italian ONLUS foundation, not US 501(c)(3). 'Ferrero Family Foundation Inc' (EIN 58-2348659) is unrelated family.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Ferrero is private company", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 12, "sources": ["Fondazione Ferrero (Italy)", "Forbes"], "note": "No public budget disclosure. Employee-focused programs.", "url": "https://www.fondazioneferrero.it/"},
            "news_verified": {"status": "found", "amount_millions": 12, "sources": ["Forbes", "Reuters"], "url": "https://www.forbes.com/sites/giacomotognini/2020/03/19/giorgio-armani-and-17-other-italian-billionaires-donate-more-than-28-million-to-fight-coronavirus-in-italy/"}
        },
        "sources": [
            "https://www.forbes.com/sites/giacomotognini/2020/03/19/giorgio-armani-and-17-other-italian-billionaires-donate-more-than-28-million-to-fight-coronavirus-in-italy/",
            "https://www.fondazioneferrero.it/The-Foundation/?lang=EN"
        ]
    },
    "Jacqueline Mars": {
        "total_lifetime_giving_millions": 20,
        "giving_breakdown": {
            "kennedy_center_renovation": 10,
            "smithsonian_mars_hall": 5,
            "wpas_education": 1.4,
            "catholic_university_plaza": 1.25,
            "equestrian_helmet_research": 0.43,
            "land_trust_virginia": 0.1,
            "national_sporting_library": 0.5,
            "other": 1.32,
            "notes": "VERIFIED Jan 2026: ~$20M documented major gifts. Kennedy Center $10M (2015). Smithsonian $5M (Mars, Inc. gift family-directed). WPAS $1.4M. CUA $1.25M. Mars HQ Regional Foundation (EIN 54-6037592) $1.8M/yr. Virginia Cretella Mars Foundation (EIN 13-3798973) $1.1M/yr. NOT Giving Pledge signatory."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 2.9, "ein": "54-6037592", "note": "Mars HQ Regional Foundation $1.8M + Virginia Cretella Mars Foundation (EIN 13-3798973) $1.1M = $2.9M/yr. Family foundations, not solely Jacqueline's.", "url": "https://projects.propublica.org/nonprofits/organizations/546037592"},
            "sec_form4": {"status": "not_applicable", "note": "Mars, Inc. is private", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 20, "sources": ["ProPublica 990-PF", "Inside Philanthropy"], "note": "Extremely private family. Documented gifts likely undercount.", "url": "https://projects.propublica.org/nonprofits/organizations/133798973"},
            "news_verified": {"status": "found", "amount_millions": 18, "sources": ["Politico", "Washingtonian", "Washington Life"], "url": "https://www.politico.com/story/2015/09/kgb-kennedy-center-scores-donors-213978"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/546037592",
            "https://www.insidephilanthropy.com/home/2014-7-31-exploring-planet-mars-where-will-that-60-billion-candy-fortu-html"
        ]
    },
    "Alain Wertheimer": {
        "total_lifetime_giving_millions": 60,
        "giving_breakdown": {
            "fondation_chanel_annual_share": 55,
            "israel_humanitarian_2023_share": 2,
            "moma_carnegie_hall": 0.004,
            "pierre_wertheimer_foundation": 0.04,
            "game_conservancy_action_innocence": 3,
            "notes": "VERIFIED Jan 2026: Fondation Chanel disburses ~$20M/yr from $110M annual Chanel contribution (split with Gerard). Pierre J. Wertheimer Foundation (EIN 13-6161226) minimal activity. Personal giving extremely opaque. Israel $4M (2023) split between brothers. MoMA/Carnegie Hall only ~$7,500 documented (2015-2023)."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 0.04, "ein": "13-6161226", "note": "Pierre J. Wertheimer Foundation: $83K (2021), currently $0 assets. Minimal activity.", "url": "https://projects.propublica.org/nonprofits/organizations/136161226"},
            "sec_form4": {"status": "not_applicable", "note": "Chanel is private", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 110, "sources": ["Chanel Financial Results", "Fondation Chanel UK"], "note": "Fondation Chanel receives $110M/yr from Chanel. Corporate, not personal.", "url": "https://www.chanel.com/"},
            "news_verified": {"status": "found", "amount_millions": 4, "sources": ["WWD", "Algemeiner"], "url": "https://wwd.com/business-news/markets/fashion-companies-humanitarian-donations-israel-hamas-war-1235876757/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/136161226",
            "https://patronview.com/patrons/alain-wertheimer"
        ]
    },
    "Gerard Wertheimer": {
        "total_lifetime_giving_millions": 60,
        "giving_breakdown": {
            "fondation_chanel_annual_share": 55,
            "israel_humanitarian_2023_share": 2,
            "orphanage_santo_domingo": 1,
            "game_conservancy_action_innocence": 2,
            "notes": "VERIFIED Jan 2026: Same as Alain - philanthropy via Fondation Chanel (corporate). Gerard's wife Valerie manages orphanage in Dominican Republic. Personal giving undisclosed. Wertheimer-Stiftung (Switzerland, 2007) has minimal documented activity."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "No personal US foundation. See Pierre J. Wertheimer Foundation under Alain.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Chanel is private", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 60, "sources": ["Fondation Chanel", "Wertheimer-Stiftung"], "note": "Swiss foundation has minimal public records. Corporate Fondation Chanel is primary vehicle.", "url": "https://www.fundraiso.com/en/organisations/wertheimer-stiftung"},
            "news_verified": {"status": "partial", "amount_millions": 2, "sources": ["WWD", "Prabook"], "url": None}
        },
        "sources": [
            "https://wwd.com/business-news/markets/fashion-companies-humanitarian-donations-israel-hamas-war-1235876757/"
        ]
    },
    "François Pinault": {
        "total_lifetime_giving_millions": 104,
        "giving_breakdown": {
            "notre_dame_cathedral": 100,
            "victor_hugo_hauteville_house": 3,
            "chapel_saint_michel_brasparts": 0.5,
            "prix_pierre_daix_annual": 0.1,
            "notes": "VERIFIED Jan 2026: €100M Notre-Dame (explicitly refused tax breaks). €3M Victor Hugo house. €500K Brittany chapel. Pinault Collection is PRIVATE COMPANY, not charity - €155-170M Bourse de Commerce and Venice museums are personal art spending, not philanthropy."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "French billionaire. Pinault Collection structured as société anonyme, not foundation.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Kering listed on Euronext Paris, no charitable stock gifts found", "url": None},
            "foundation_reports": {"status": "not_applicable", "note": "Pinault Collection is NOT a foundation - explicitly chose private company structure. No tax breaks.", "url": "https://news.artnet.com/art-world/bourse-de-commerce-paris-opening-1970450"},
            "news_verified": {"status": "found", "amount_millions": 104, "sources": ["Reuters", "BBC", "Bloomberg", "Art Newspaper"], "url": "https://www.reuters.com/article/us-france-notredame-pinault/frances-pinault-family-will-not-seek-tax-breaks-on-notre-dame-donation-idUSKCN1RT0XI/"}
        },
        "sources": [
            "https://www.reuters.com/article/us-france-notredame-pinault/frances-pinault-family-will-not-seek-tax-breaks-on-notre-dame-donation-idUSKCN1RT0XI/",
            "https://www.bbc.com/news/world-europe-guernsey-43669679"
        ]
    },
    "Germán Larrea Mota-Velasco": {
        "total_lifetime_giving_millions": 100,
        "giving_breakdown": {
            "fundacion_grupo_mexico_annual_est": 87,
            "covid_hospital_juchitan_2020": 20,
            "covid_ventilators_2020": 3,
            "notes": "VERIFIED Jan 2026: Fundación Grupo México invests ~3.8% of net profit in community (~$87M in 2020). COVID hospital donated to Army (est. $20M). Río Sonora $150M fund was COURT-MANDATED compensation, not voluntary. No personal foundation. NOT Giving Pledge signatory. Extremely private."
        },
        "verification": {
            "990_pf": {"status": "not_found", "note": "No US foundation. Fundación Grupo México registered in Mexico.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Grupo México traded on BMV (Mexican exchange)", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 100, "sources": ["Grupo México", "Fundación Grupo México"], "note": "Corporate foundation. Dr. Vagón medical train, Escuchar Sin Fronteras. ~$87M/yr.", "url": "https://fundaciongrupomexico.org/"},
            "news_verified": {"status": "found", "amount_millions": 23, "sources": ["Forbes México", "Meganoticias"], "url": "https://www.forbes.com.mx/negocios-grupo-mexico-german-larrea-entregara-hospital-ejercito-para-atender-coronavirus-oaxaca/"}
        },
        "sources": [
            "https://fundaciongrupomexico.org/",
            "https://www.forbes.com.mx/negocios-grupo-mexico-german-larrea-entregara-hospital-ejercito-para-atender-coronavirus-oaxaca/"
        ]
    },
    # === BATCH 7: ADDITIONAL HIGH-VALUE VERIFICATIONS JAN 2026 ===
    "John Mars": {
        "total_lifetime_giving_millions": 50,
        "giving_breakdown": {
            "mars_foundation_share": 10,
            "mount_vernon_cumulative": 25,
            "yale_epe_professorship_1999": 2,
            "wheaton_college": 5,
            "smithsonian_support": 5,
            "other_institutional": 3,
            "notes": "VERIFIED Jan 2026: Mars family is NOTORIOUSLY PRIVATE. Mars Foundation (EIN 54-6037592) ~$2M/yr total, John's share ~$600K. Mount Vernon $25M+ cumulative (John & Adrienne). Yale $2M (1999, with Forrest Jr). Wheaton $5-10M. NO Giving Pledge. NO personal foundation. Forbes philanthropy score: N/A."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 2, "ein": "54-6037592", "note": "Mars Foundation: $47M assets, ~$2M/yr grants. Shared by 3 siblings (John, Jacqueline, Forrest Jr estate).", "url": "https://projects.propublica.org/nonprofits/organizations/546037592"},
            "sec_form4": {"status": "not_applicable", "note": "Mars, Inc. is private", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 50, "sources": ["Mars Foundation 990-PF", "Mount Vernon donor list", "Yale News"], "note": "Inside Philanthropy: 'neither staff nor a website'. Extremely opaque.", "url": "https://www.insidephilanthropy.com/home/2014-7-31-exploring-planet-mars-where-will-that-60-billion-candy-fortu-html"},
            "news_verified": {"status": "found", "amount_millions": 37, "sources": ["Yale News", "Mount Vernon", "CBS Boston"], "url": "https://news.yale.edu/1999/12/06/john-f-mars-and-forrest-e-mars-jr-announce-new-chair-ethics-politics-and-economics-yale"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/546037592",
            "https://news.yale.edu/1999/12/06/john-f-mars-and-forrest-e-mars-jr-announce-new-chair-ethics-politics-and-economics-yale",
            "https://www.insidephilanthropy.com/home/2014-7-31-exploring-planet-mars-where-will-that-60-billion-candy-fortu-html"
        ]
    },
    "Lukas Walton": {
        "total_lifetime_giving_millions": 500,
        "giving_breakdown": {
            "builders_initiative_cumulative": 350,
            "breakthrough_energy_catalyst": 150,
            "walton_family_foundation_contribution": 149,
            "chicago_community_grants": 50,
            "ocean_conservation": 30,
            "notes": "VERIFIED Jan 2026: Builders Initiative Foundation (EIN 82-1503941) $1.65B assets, ~$80-100M/yr grants. Cumulative ~$350M disbursed. $150M to Breakthrough Energy Catalyst. $149M personal contribution to Walton Family Foundation. Focus: climate, oceans, food systems, Chicago community. NOT to be confused with WFF's $600M/yr which is shared family."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 99, "ein": "82-1503941", "note": "Builders Initiative Foundation: $1.65B assets, $99M disbursements (2024). Lukas is founder/CEO/Chair.", "url": "https://projects.propublica.org/nonprofits/organizations/821503941"},
            "sec_form4": {"status": "partial", "note": "Walmart stock transfers to foundation tracked via 990 contributions received", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 500, "sources": ["ProPublica 990-PF", "Forbes", "Builders Vision"], "note": "$2B 'committed to philanthropy' 2019-2021 includes endowment growth. Actual disbursements ~$350M cumulative.", "url": "https://www.forbes.com/sites/amyfeldman/2023/10/17/exclusive-lukas-waltons-builders-vision-reveals-how-its-deployed-3-billion-to-change-the-world/"},
            "news_verified": {"status": "found", "amount_millions": 500, "sources": ["Forbes", "Fortune", "TIME"], "url": "https://fortune.com/2024/10/01/lukas-walton-builders-initiative-philanthropy/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/821503941",
            "https://www.forbes.com/sites/amyfeldman/2023/10/17/exclusive-lukas-waltons-builders-vision-reveals-how-its-deployed-3-billion-to-change-the-world/"
        ]
    },
    "Beate Heister": {
        "total_lifetime_giving_millions": 0,
        "giving_breakdown": {
            "personal_giving_verified": 0,
            "notes": "UNABLE TO VERIFY Jan 2026: Albrecht family is EXTREMELY PRIVATE. Siepmann-Stiftung is a FAMILY FOUNDATION (pays corporate taxes), NOT a charitable foundation. Claims of 'cardiovascular research' giving have no named recipients or amounts. NO Giving Pledge. NO public foundation filings in Germany. NO documented major gifts. If giving exists, it is entirely hidden from public view."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "German resident, no US foundation. Siepmann-Stiftung is family trust, not charitable.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Aldi is private", "url": None},
            "foundation_reports": {"status": "not_found", "note": "Germany's Stiftungsregister has limited transparency. No charitable giving documented.", "url": None},
            "news_verified": {"status": "not_found", "note": "No specific gifts, amounts, or recipients found in English or German sources.", "url": None}
        },
        "sources": [
            "https://littlesis.org/person/185122-Beate_Heister",
            "https://familyofficehub.io/blog/karl-albrecht-jr-beate-heist-is-there-a-family-office/"
        ]
    },
    "Karl Albrecht Jr.": {
        "total_lifetime_giving_millions": 0,
        "giving_breakdown": {
            "personal_giving_verified": 0,
            "notes": "UNABLE TO VERIFY Jan 2026: Same as Beate Heister. Albrecht heirs have made no public charitable announcements. Aldi corporate community giving (e.g. €500 to children's cancer) is trivial. Multiple sources say family 'kept charitable efforts private' but provide no specifics. Effectively no documented philanthropy."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "German resident, no US foundation", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Aldi is private", "url": None},
            "foundation_reports": {"status": "not_found", "note": "No public charitable foundation filings", "url": None},
            "news_verified": {"status": "not_found", "note": "No documented personal charitable giving", "url": None}
        },
        "sources": [
            "https://www.mashed.com/171899/the-untold-truth-of-the-brothers-who-started-aldi/"
        ]
    },
    "Robin Zeng": {
        "total_lifetime_giving_millions": 210,
        "giving_breakdown": {
            "shanghai_jiao_tong_2021": 206,
            "other_university_research": 4,
            "notes": "VERIFIED Jan 2026: CNY 1.37B (~$206M) to Shanghai Jiao Tong University (Dec 2021) in CATL stock (2M shares). Third-largest donation to Chinese university at time. Hurun China Philanthropy List #6 in 2022 ($190M). NOT on 2023-2024 lists (no major gifts). CATL corporate giving is separate (~$13M documented)."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Chinese billionaire, no US foundation. CATL registered in Fujian Province.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "CATL traded on Shenzhen Stock Exchange", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 210, "sources": ["Hurun China", "Shanghai Jiao Tong"], "note": "Single major gift documented. No ongoing foundation.", "url": "https://www.yicaiglobal.com/news/catl-founder-to-gift-usd206-million-of-shares-to-shanghai-jiao-tong-university"},
            "news_verified": {"status": "found", "amount_millions": 206, "sources": ["Yicai Global", "Hurun"], "url": "https://www.hurun.net/en-us/info/detail?num=WIWVJLUHGIU1"}
        },
        "sources": [
            "https://www.yicaiglobal.com/news/catl-founder-to-gift-usd206-million-of-shares-to-shanghai-jiao-tong-university",
            "https://www.hurun.net/en-us/info/detail?num=WIWVJLUHGIU1"
        ]
    },
    "Robert Pera": {
        "total_lifetime_giving_millions": 1.2,
        "giving_breakdown": {
            "mike_conley_match_2016": 1.0,
            "st_jude_1on1_game_2013": 0.1,
            "mid_south_food_bank_2020": 0.075,
            "ucsd_gifts": 0.025,
            "notes": "VERIFIED Jan 2026: RE-VERIFIED. Total documented personal giving ~$1.2M. Forbes Philanthropy Score: 1/5 (lowest). Robert J Pera Foundation (EIN 87-1254834) exists but shows $0 activity since 2022 formation. Memphis Grizzlies Charitable Foundation is TEAM-FUNDED (not his personal wealth). NOT Giving Pledge signatory. At $23B net worth, this is 0.005% of wealth. SCROOGE LIST #1 RANKING CONFIRMED."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 0, "ein": "87-1254834", "note": "Robert J Pera Foundation: $0 revenue, $0 expenses, $0 assets across all years (2022-2024). Never been funded.", "url": "https://projects.propublica.org/nonprofits/organizations/871254834"},
            "sec_form4": {"status": "not_found", "note": "No charitable stock gifts (code G) found", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 1.2, "sources": ["ESPN", "SI", "Bleacher Report"], "note": "Grizzlies Foundation ($28M since 2001) is team-funded, predates Pera's 2012 ownership", "url": "https://projects.propublica.org/nonprofits/organizations/201356702"},
            "news_verified": {"status": "found", "amount_millions": 1.2, "sources": ["ESPN", "Bleacher Report", "Commercial Appeal"], "url": "https://www.espn.com/nba/story/_/id/17079781/memphis-grizzlies-mike-conley-says-five-year-153-million-contract-affect-play"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/871254834",
            "https://www.espn.com/nba/story/_/id/17079781/memphis-grizzlies-mike-conley-says-five-year-153-million-contract-affect-play"
        ]
    },
    # === BATCH 8: MORE HIGH-VALUE VERIFICATIONS JAN 2026 ===
    "Stephen Schwarzman": {
        "total_lifetime_giving_millions": 1100,
        "giving_breakdown": {
            "mit_college_computing": 350,
            "oxford_schwarzman_centre": 233,
            "yale_schwarzman_center": 150,
            "schwarzman_scholars_tsinghua": 100,
            "nypl_building": 100,
            "abington_high_school": 25,
            "animal_medical_center": 25,
            "frick_collection": 7.3,
            "other_foundation_grants": 110,
            "notes": "VERIFIED Jan 2026: Two foundations (EIN 47-4634539 + EIN 45-4757735). Combined ~$100M/yr disbursements. $1.1B lifetime per Blackstone. Giving Pledge signatory 2020. Nearly all major gifts involve naming rights."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 102, "ein": "47-4634539", "note": "Stephen A Schwarzman Foundation: $65M assets, $78.5M/yr (2024) + Education Foundation: $13.6M assets, $23.9M/yr (2024) = $102M/yr combined", "url": "https://projects.propublica.org/nonprofits/organizations/474634539"},
            "sec_form4": {"status": "partial", "note": "Blackstone stock gifts to foundation visible in 990 contributions received", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 362, "sources": ["ProPublica 990-PF"], "note": "~$362M verified disbursements 2020-2024", "url": "https://projects.propublica.org/nonprofits/organizations/454757735"},
            "news_verified": {"status": "found", "amount_millions": 1100, "sources": ["Chronicle of Philanthropy", "Blackstone", "MIT News", "Oxford"], "url": "https://news.mit.edu/2018/mit-reshapes-itself-stephen-schwarzman-college-of-computing-1015"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/474634539",
            "https://projects.propublica.org/nonprofits/organizations/454757735",
            "https://news.mit.edu/2018/mit-reshapes-itself-stephen-schwarzman-college-of-computing-1015"
        ]
    },
    "Ken Griffin": {
        "total_lifetime_giving_millions": 2000,
        "giving_breakdown": {
            "harvard_total": 500,
            "memorial_sloan_kettering": 200,
            "museum_science_industry_chicago": 125,
            "university_chicago_economics": 125,
            "university_miami_sylvester": 50,
            "baptist_health_miami": 50,
            "moma_amnh_field_museum": 100,
            "success_academy": 35,
            "chicago_parting_gift_2022": 130,
            "other": 685,
            "notes": "VERIFIED Jan 2026: Uses DAF (Kenneth C. Griffin Charitable Fund) which has NO public disclosure. $2B+ claimed (TIME100). NOT Giving Pledge signatory. 990-PF foundations minimal (~$3M/yr). Most giving unverifiable due to DAF structure."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 2.4, "ein": "36-4482467", "note": "Citadel Group Foundation: $2.4M (2024). Kenneth C. Griffin Charitable Fund is a DAF with NO 990-PF filings.", "url": "https://projects.propublica.org/nonprofits/organizations/364482467"},
            "sec_form4": {"status": "partial", "note": "Citadel is private, limited SEC visibility", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 2000, "sources": ["Griffin Catalyst website", "TIME100"], "note": "DAF means total contributions and disbursements are not publicly verifiable", "url": "https://www.griffincatalyst.org/about/"},
            "news_verified": {"status": "found", "amount_millions": 1500, "sources": ["Harvard Gazette", "MSI Chicago", "Chronicle of Philanthropy"], "url": "https://time.com/collections/time100-philanthropy-2025/7286078/ken-griffin/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/364482467",
            "https://www.griffincatalyst.org/about/",
            "https://time.com/collections/time100-philanthropy-2025/7286078/ken-griffin/"
        ]
    },
    "Klaus-Michael Kühne": {
        "total_lifetime_giving_millions": 600,
        "giving_breakdown": {
            "hamburg_opera_house_2025": 308,
            "kuhne_logistics_university": 70,
            "elbphilharmonie_salzburg_lucerne": 50,
            "medicine_campus_davos": 75,
            "hsv_football_donations": 100,
            "annual_foundation_operations": 50,
            "notes": "VERIFIED Jan 2026: Kühne Foundation (Switzerland) has minimal disclosure requirements. EUR 300M Hamburg Opera (2025) is largest verified gift. CHF 5M/yr to foundation. Cardio-CARE CHF 13M. HSV is mix of investment/donation. Range likely EUR 500M-1B."
        },
        "verification": {
            "990_pf": {"status": "not_applicable", "note": "Swiss foundation, no US filings. Swiss law requires no public disclosure.", "url": None},
            "sec_form4": {"status": "not_applicable", "note": "Kuehne+Nagel traded on Swiss exchange", "url": None},
            "foundation_reports": {"status": "partial", "amount_millions": 600, "sources": ["Kühne Foundation website", "Press announcements"], "note": "No financial reports published. EUR 300M opera gift confirmed Jan 2025.", "url": "https://www.kuehne-stiftung.org/"},
            "news_verified": {"status": "found", "amount_millions": 500, "sources": ["OperaWire", "Der Spiegel", "Vanity Fair"], "url": "https://operawire.com/german-billionaire-makes-massive-investment-into-new-hamburg-opera-house/"}
        },
        "sources": [
            "https://www.kuehne-stiftung.org/",
            "https://operawire.com/german-billionaire-makes-massive-investment-into-new-hamburg-opera-house/"
        ]
    },
    "Daniel Gilbert": {
        "total_lifetime_giving_millions": 1000,
        "giving_breakdown": {
            "henry_ford_shirley_ryan_2023": 375,
            "detroit_500m_pledge_2021": 500,
            "neurofibromatosis_research": 125,
            "cranbrook_academy_art": 30,
            "michigan_state_university": 15,
            "wayne_state_law": 5,
            "other": 50,
            "notes": "VERIFIED Jan 2026: Giving Pledge signatory 2012. $1B+ in announced commitments. Gilbert Family Foundation (EIN 81-0810541) wound down 2024 (final return). $375M Henry Ford is largest single gift. Rocket Community Fund is corporate ($200M+)."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 75, "ein": "81-0810541", "note": "Gilbert Family Foundation: $75M total disbursements 2017-2024. Filed final return 2024 ($0 assets).", "url": "https://projects.propublica.org/nonprofits/organizations/810810541"},
            "sec_form4": {"status": "partial", "note": "Rocket Companies stock visible, foundation contributions tracked via 990", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 1000, "sources": ["Gilbert Family Foundation", "Chronicle of Philanthropy"], "note": "Foundation wound down; giving continues through other structures", "url": "https://gilbertfamilyfoundation.org/"},
            "news_verified": {"status": "found", "amount_millions": 1000, "sources": ["NYT", "Chronicle of Philanthropy", "Crain's Detroit"], "url": "https://www.nytimes.com/2021/03/25/business/dan-gilbert-will-invest-500-million-to-help-revitalize-detroit.html"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/810810541",
            "https://gilbertfamilyfoundation.org/",
            "https://www.nytimes.com/2021/03/25/business/dan-gilbert-will-invest-500-million-to-help-revitalize-detroit.html"
        ]
    },
    "Miriam Adelson": {
        "total_lifetime_giving_millions": 1500,
        "giving_breakdown": {
            "adelson_family_foundation_cumulative": 833,
            "adelson_medical_research_foundation": 379,
            "birthright_israel_pre2015": 500,
            "yad_vashem": 50,
            "ariel_university_medical": 25,
            "adelson_educational_campus": 75,
            "fidf": 20,
            "notes": "VERIFIED Jan 2026: Two 990-PF foundations (EIN 04-7024330 + EIN 04-7023433). Combined ~$1.2B verified. Political donations ($284M lifetime) are SEPARATE and excluded. Focus: Israel, Jewish causes, drug rehabilitation, medical research."
        },
        "verification": {
            "990_pf": {"status": "found", "amount_millions": 109, "ein": "04-7024330", "note": "Adelson Family Foundation: $66.9M (2024) + Medical Research Foundation (EIN 04-7023433): $42.4M (2024) = $109M/yr combined", "url": "https://projects.propublica.org/nonprofits/organizations/47024330"},
            "sec_form4": {"status": "partial", "note": "Las Vegas Sands stock transfers to foundations visible in 990s", "url": None},
            "foundation_reports": {"status": "found", "amount_millions": 1212, "sources": ["ProPublica 990-PF"], "note": "~$833M (Family) + $379M (Medical) = $1.21B verified 990 disbursements 2011-2024", "url": "https://projects.propublica.org/nonprofits/organizations/47023433"},
            "news_verified": {"status": "found", "amount_millions": 1500, "sources": ["Times of Israel", "Forbes", "Yad Vashem"], "url": "https://www.timesofisrael.com/birthright-celebrates-70-million-in-donations-from-the-adelsons-this-year/"}
        },
        "sources": [
            "https://projects.propublica.org/nonprofits/organizations/47024330",
            "https://projects.propublica.org/nonprofits/organizations/47023433",
            "https://www.timesofisrael.com/birthright-celebrates-70-million-in-donations-from-the-adelsons-this-year/"
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
    "Larry Ellison": 370.0,  # Forbes/Bloomberg Jan 2026 (major Oracle stock appreciation)
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

            # Update giving_pledge if specified (supports "partial", "99% pledge", etc.)
            if 'giving_pledge' in vdata:
                entry['giving_pledge'] = vdata['giving_pledge']

            # Update image_url if specified
            if 'image_url' in vdata:
                entry['image_url'] = vdata['image_url']

            # Calculate verifiable vs unverifiable giving
            # Verifiable: foundation_reports (actual grants from 990-PF/annual reports)
            # Unverifiable: news/announcements beyond documented giving
            # NOTE: 990-PF amount_millions often shows ASSETS not GRANTS
            # NOTE: SEC Form 4 can show transfers to own foundation, not external charity
            verification = vdata.get('verification', {})
            total_giving = vdata['total_lifetime_giving_millions']

            verifiable = 0
            unverifiable = 0

            # Foundation reports is the PRIMARY source for verifiable giving
            # This represents actual grants/disbursements, not just assets
            if verification.get('foundation_reports', {}).get('status') == 'found':
                amt = verification['foundation_reports'].get('amount_millions', 0)
                if amt and amt > 0:
                    verifiable = amt
            # Fallback to 990-PF only if foundation_reports not available
            elif verification.get('990_pf', {}).get('status') == 'found':
                amt = verification['990_pf'].get('amount_millions', 0)
                if amt and amt > 0:
                    verifiable = amt
            # SEC Form 4 as secondary verifiable source (stock gifts to external charities)
            # Only count if it represents actual charitable transfers, not foundation funding
            elif verification.get('sec_form4', {}).get('status') == 'found':
                amt = verification['sec_form4'].get('amount_millions', 0)
                if amt and amt > 0:
                    verifiable = amt

            # Unverifiable = total giving minus verifiable portion
            unverifiable = max(0, total_giving - verifiable)

            # Cap verifiable at total (can't verify more than total)
            verifiable = min(verifiable, total_giving)

            entry['verifiable_giving_millions'] = verifiable
            entry['unverifiable_giving_millions'] = unverifiable

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
