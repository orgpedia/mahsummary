from datetime import datetime, timedelta
import json
import re
import sys

from operator import itemgetter
from pathlib import Path

import yaml

from more_itertools import flatten, first
from jinja2 import Environment, FileSystemLoader, select_autoescape

DistrictDirectory = '.bak/districts'
DistrictNames = ['Ahmednagar', 'Akola', 'Amravati', 'Aurangabad', 'Beed', 'Bhandara', 'Buldhana',
                 'Chandrapur', 'Dhule', 'Gadchiroli', 'Gondia', 'Hingoli', 'Jalgaon', 'Jalna',
                 'Kolhapur', 'Latur', 'Mumbai_City', 'Mumbai_Suburban', 'Nagpur', 'Nanded',
                 'Nandurbar', 'Nashik', 'Osmanabad', 'Palghar', 'Parbhani', 'Pune', 'Raigad',
                 'Ratnagiri', 'Sangli', 'Satara', 'Sindhudurg', 'Solapur', 'Thane', 'Wardha',
                 'Washim', 'Yavatmal']

def build_district_summary(gr_dir, doc_infos):
    doc_info_dict = {}
    for district_name in DistrictNames:
        d = district_name
        d =  d.replace('_City', '')
        doc_info_dict[d] = []

        district_infos = []
        for doc_info in doc_infos:
            if 'districts' in doc_info and d in doc_info['districts']:
                district_infos.append(doc_info)

        if len(district_infos) <= 8:
            doc_info_dict[d] = district_infos
        else:
            def score_info(doc_info):
                score = doc_info['district_counts'][d]/len(doc_info['district_counts'])
                return score
            
            di_sorted = sorted(district_infos, key=score_info, reverse=True)
            doc_info_dict[d] = di_sorted[:10]
        #print(d, len(doc_info_dict[d]))
    return doc_info_dict

       
        
def build_dept_summary(gr_dir, doc_infos):
    # TODO separate in two methods annotate doc and build_dept_summary
    def extract_money(doc_text):
        # r'Rs\.\s*(?:[\d,]+\s*)+\S+'
        pattern = r'(?:(?:Rs\.\s)?\d+(?:\.\d+)?\s(?:crore|lakhs))|\b\d+\b'
        amounts = [ re.findall(pattern, ln.replace(',','')) for ln in doc_text.split('\n') ]
        amounts = list(flatten(amounts))

        for m in ['crore', 'lakh']:
            m_amounts = [ a for a in amounts if m in a]
            f_amounts = [ a.replace('Rs.','').replace(m, '') for a in m_amounts ]
            mf_amounts = sorted(zip(m_amounts, f_amounts), key=itemgetter(1))
            if mf_amounts:
                return mf_amounts[-1][0]
        return None

    def split_doc(doc_path):
        year = doc_path.name[:4]
        doc_text = doc_path.read_text()
        doc_lines = [ln for ln in doc_text.split('\n') if ln and ln[0] != '#']

        year_strs = [f' {year}', f'.{year}', f'/{year}']

        sub_end_idx, body_start_idx = 0, 0
        for idx, line in enumerate(doc_lines[:10]):
            if 'Government' in line and 'Maharashtra' in line:
                sub_end_idx = idx

            if any(y in line for y in year_strs) and ('date' in line.lower() or 'as of' in line.lower()):
                body_start_idx = idx

        sub_end_idx = 2 if sub_end_idx == 0 else sub_end_idx
        body_start_idx = 8 if body_start_idx == 0 else body_start_idx

        return '\n'.join(doc_lines[:sub_end_idx]), '\n'.join(doc_lines[body_start_idx:])


    
    def find_districts(input_path, district_names):
        district_names = [d.replace(' City', '') for d in district_names] 
        doc_subject, doc_body = split_doc(input_path)
        district_counts = {}        
        for d in district_names:
            cnt = doc_subject.count(d) + doc_body.count(d)
            if cnt:
                district_counts[d] = cnt
        return district_counts

    def find_subject(doc_path):
        lines = [ln for ln in doc_path.read_text().split('\n') if ln and ln[0] != '#']
        line_idx = 0
        for idx, line in enumerate(lines):
            if line.startswith('The Government of Maharashtra') or line.startswith('Government of Maharashtra'):
                line_idx = idx
                break

            if line.endswith('Government of Maharashtra') or line.endswith('Maharashtra Govt'):
                line_idx = idx + 1
                break

            if idx > 10:
                assert False, f'Unable to find line in {doc_path}'
                
        mr_doc_path = doc_path.parent / doc_path.name.replace('.en.', '.mr.')
        mr_lines = [ln for ln in mr_doc_path.read_text().split('\n') if ln and ln[0] != '#']
        mr_subject = ' '.join(mr_lines[:line_idx])
        return mr_subject

    district_names = [d.replace('_', ' ') for d in DistrictNames]
    doc_info_dict = {}
    for doc_info in doc_infos:
        if doc_info['dept'] == 'Soil & Water Conservation Department':
            doc_info['dept'] = 'Soil and Water Conservation Department'
            
        doc_path = gr_dir / Path(doc_info['dept'].replace(' ','_')) / f'{doc_info["code"]}.pdf.en.txt'
        if not doc_path.exists():
            continue
        
        doc_text = doc_path.read_text()
        doc_text_lower = doc_text.lower()

        funds_amount = None
        if any(m in doc_text for m in ['crore', 'lakh']):
            doc_type = 'Funds'
            funds_amount = extract_money(doc_text)
        elif any(p in doc_text_lower for p in ['posting', 'transfer', 'seniority', 'temporary']):
            doc_type = 'Personnel'
        else:
            doc_type = 'Miscellaneous'
        
        doc_info['doc_type'] = doc_type
        doc_info['funds_amount'] = funds_amount
        doc_info['en_doc_path'] = doc_path
        
        #doc_info['districts'] = find_districts(doc_text, district_names)

        doc_info['district_counts'] = find_districts(doc_path, district_names)        
        doc_info['districts'] = ', '.join(d for (d, c) in doc_info['district_counts'].items())
        
        doc_info['mr_text'] = find_subject(doc_path)

        print(f"{doc_info['en_doc_path'].name}:{doc_info['text'][:70]}|{doc_info['districts']}")
        #print(f"{doc_info['en_doc_path']}")
        doc_info_dict.setdefault(doc_info['dept'], []).append(doc_info)
        
    return doc_info_dict


class DeptInfo:
    def __init__(self, name, dept_info_dict):
        for (k, v) in dept_info_dict.items():
            setattr(self, k, v)

class SiteInfo:
    def __init__(self, site_info):
        for (k, v) in site_info.items():
            setattr(self, k, v)

    # so that we can get date_str also in specified languages
    def set_date(self, dt, lang):
        if not dt:
            self.week_num = ''
            self.start_date_str = ''
            self.end_date_str = ''
            return

        self.year = dt.year
        self.week_num = dt.isocalendar()[1]
        week_str = f'{dt.year}-W{self.week_num}'

        start_date = datetime.strptime(week_str + '-1', "%Y-W%W-%w").date()
        end_date = start_date + timedelta(days=5)
        
        self.start_date_str = start_date.strftime("%d %B %Y")
        self.end_date_str = end_date.strftime("%d %B %Y")

        if lang != 'en':
            self.start_date_str = convert_date_str(self.start_date_str, self)
            self.end_date_str = convert_date_str(self.end_date_str, self)
            self.year = convert_num(self.year, self)
            self.week_num = convert_num(self.week_num, self)

def convert_num(d, site_info):
    r = []
    for c in str(d):
        t = getattr(site_info, c) if c not in '.,' else c
        r.append(t)
    return ''.join(r)

def convert_money(m, site_info):
    m = m.lower().strip() if m else m
    if not m:
        return ''
    
    for s in ['rs.', 'lakhs', 'crores', 'lakh', 'crore']:
        m = m.replace(s, getattr(site_info, s))

    print(m)
    num_str = first(n for n in m.split() if n.replace(',','').replace('.','').isdigit())
    m = m.replace(num_str, convert_num(num_str, site_info))
    return m

def convert_date_str(date_str, site_info):
    d, m, y = date_str.split()
    return f'{convert_num(d, site_info)} {getattr(site_info, m)} {convert_num(y, site_info)}'

class DocInfo:
    def __init__(self, doc_info, site_info, lang='en'):
        for (k, v) in doc_info.items():
            setattr(self, k, v)
            
        self.lang = lang
        self.site_info = site_info
        
        if lang != 'en':
            self.text = self.mr_text
            if self.districts:
                dists = self.districts.split(',')
                dists = [dists] if isinstance(dists, str) else dists
                print(dists)
                self.districts = ', '.join(getattr(site_info, d.strip()) for d in dists)
                
            self.num_pages = convert_num(self.num_pages, site_info)
            self.doc_type = getattr(site_info, self.doc_type)
            self.funds_amount = convert_money(self.funds_amount, site_info)
            self.dept = getattr(site_info, self.dept)

    @property
    def date_str(self):
        date_str = self.date.strftime('%d %b %Y')
        if self.lang != 'en':
            date_str = convert_date_str(date_str, self.site_info)
        return date_str

SiteInfoGlobal = None
def get_site_info(lang):
    global SiteInfoGlobal
    
    if not SiteInfoGlobal:
        SiteInfoGlobal = yaml.load(Path('site.yml').read_text(), Loader=yaml.FullLoader)

    input_dict = {'lang_selected': lang, 'lang': lang}
    for key, key_dict in SiteInfoGlobal.items():
        input_dict[key] = key_dict[lang]
    return SiteInfo(input_dict)

def gen_index_html(lang, jinja_env):
    if lang == 'en':
        template = jinja_env.get_template('index.html')
    else:
        template = jinja_env.get_template(f'index-{lang}.html')
                
    site_info = get_site_info(lang)
    site_info.title = site_info.mahGRs

    html_file = Path(f"output/{lang}/index.html")
    html_file.write_text(template.render(site=site_info))
    
    

def gen_dept_top_html(dept_names, doc_infos_dict, lang, year, week_num, jinja_env):
    def get_url(name, lang):
        return f"{year}-W{week_num}-{name.replace(' ','')}.html"

    def get_date(doc_infos_dict):
        first_info = first(flatten(doc_infos_dict.values()), default=None)
        if first_info:
            return first_info['date']
    
    template = jinja_env.get_template('top-level.html')
    site_info = get_site_info(lang)
    site_info.set_date(get_date(doc_infos_dict), lang)
    site_info.title = site_info.dept_title

    dept_infos = [(getattr(site_info, name), get_url(name, lang), convert_num(len(doc_infos_dict.get(name, [])), site_info))
                  for name in dept_names
                  ]

    html_file = Path(f"output/{lang}/dept/{year}-W{week_num}-summary.html")
    html_file.write_text(template.render(site=site_info, depts=dept_infos))

    html_file = Path(f"output/{lang}/dept/summary.html")
    html_file.write_text(template.render(site=site_info, depts=dept_infos))
    

def gen_district_top_html(district_names, doc_infos_dict, lang, year, week_num, jinja_env):
    def get_url(name, lang):
        return f"{year}-W{week_num}-{name.replace(' ','')}.html"

    def get_date(doc_infos_dict):
        first_info = first(flatten(doc_infos_dict.values()), default=None)
        if first_info:
            return first_info['date']
    
    template = jinja_env.get_template('top-level.html')
    site_info = get_site_info(lang)
    site_info.set_date(get_date(doc_infos_dict), lang)
    
    site_info.title = site_info.district_title
    district_infos = [(getattr(site_info, name), get_url(name, lang), convert_num(len(doc_infos_dict.get(name, [])), site_info))
                  for name in district_names
                  ]

    html_file = Path(f"output/{lang}/dist/{year}-W{week_num}-summary.html")
    html_file.write_text(template.render(site=site_info, depts=district_infos))

    html_file = Path(f"output/{lang}/dist/summary.html")
    html_file.write_text(template.render(site=site_info, depts=district_infos))
    
    

def gen_dept_summary_html(dept_name, doc_infos, lang, year, week_num, jinja_env):
    result_doc_dict = {}
    site_info = get_site_info(lang)    

    doc_infos.sort(key=itemgetter('doc_type'))
    for doc_info_dict in doc_infos:
        doc_info = DocInfo(doc_info_dict, site_info, lang)
        result_doc_dict.setdefault(doc_info.doc_type, []).append(doc_info)

    template = jinja_env.get_template('summary.html')

    site_info.set_date(doc_infos[0]['date'], lang)
    site_info.title = f'{site_info.weekly_summary}: {getattr(site_info, dept_name)}'
    site_info.doc_type = 'department'

    dept_file_name = dept_name.replace(' ', '')
    html_file = Path(f"output/{lang}/dept/{year}-W{week_num}-{dept_file_name}.html")
    html_file.write_text(template.render(site=site_info, dept_name=dept_name, depts=result_doc_dict))


def gen_district_summary_html(district_name, doc_infos, lang, year, week_num, jinja_env):
    site_info = get_site_info(lang)
    result_doc_dict = {}
    doc_infos.sort(key=itemgetter('dept'))
    for doc_info_dict in doc_infos:
        doc_info = DocInfo(doc_info_dict, site_info, lang)
        result_doc_dict.setdefault(doc_info.dept, []).append(doc_info)

    template = jinja_env.get_template('summary.html')
    
    site_info.set_date(doc_infos[0]['date'], lang)    
    site_info.title = f'{site_info.weekly_summary}: {getattr(site_info, district_name)} {site_info.district}'
    site_info.doc_type = 'district'
        
    district_file_name = district_name.replace(' ', '')
    
    html_file = Path(f"output/{lang}/dist/{year}-W{week_num}-{district_file_name}.html")
    html_file.write_text(template.render(site=site_info, dept_name=district_name, depts=result_doc_dict))

def gen_archive_html(lang, jinja_env):
    def build_dict(paths):
        r = {}
        for p in paths:
            y, w, _ = p.name.split('-')
            w = w[1:]
            if lang != 'en':
                y = convert_num(y, site_info)
                w = convert_num(w, site_info)
            r.setdefault(y, []).append(w)
        return r

    site_info = get_site_info(lang)    
    dept_archive_paths = list(Path(f"output/{lang}/dept/").glob("*-summary.html"))
    dept_archive = build_dict(dept_archive_paths)
    site_info.title = site_info.archive_title
    
    dist_archive_paths = Path(f"output/{lang}/dist/").glob("*-summary.html")
    dist_archive = build_dict(dist_archive_paths)
    
    template = jinja_env.get_template('archive.html')

    
    html_file = Path(f"output/{lang}/archive.html")
    html_file.write_text(template.render(site=site_info, dept_archive=dept_archive, district_archive=dist_archive))


def get_week_document_infos(gr_dir, year, wk_num):
    doc_infos = list(flatten(json.loads(f.read_text()).values() for f in gr_dir.glob('*/GRs.json')))
    [i.__setitem__('date', datetime.strptime(i['date'], "%d-%m-%Y").date()) for i in doc_infos ]

    if wk_num == -1:
        max_date = max((i['date'] for i in doc_infos), default=None)
        if not max_date:
            return []
        wk_num = max_date.isocalendar()[1]
    
    doc_infos = [i for i in doc_infos if i['date'].isocalendar()[1] == wk_num and i['date'].year == year]
    return doc_infos, year, wk_num

def get_searchdoc_dict(doc_info):
    doc = {}
    doc["idx"] = doc_info['code']    
    doc["text"] = doc_info['text']
    doc["districts"] = doc_info['districts']
    doc["date"] = doc_info['date'].strftime("%d %B %Y")
    doc["url"] = doc_info['url']
    doc["num_pages"] = doc_info['num_pages']
    doc["doc_type"] = doc_info['doc_type']
    doc["funds_amount"] = doc_info['funds_amount']
    doc["dept"] = doc_info['dept']
    return doc


def write_search_index(search_doc_dicts):
    from lunr import lunr


    lunrIdx = lunr(ref="idx", fields=["text", "dept"], documents=search_doc_dicts)

    search_index_file = Path("lunr.idx.json")
    search_index_file.write_text(json.dumps(lunrIdx.serialize(), separators=(',', ':')))

    docs_file = Path("docs.json")
    docs_file.write_text(json.dumps(search_doc_dicts, separators=(',', ':')))


def main():
    if len(sys.argv) < 1:
        print('Usage: {sys.argv[0]} <gr_dir> [<week_num>] [<lang>]')
    
    gr_dir = Path(sys.argv[1])
    dept_names = sorted(p.name.replace('_', ' ') for p in gr_dir.glob('*'))
    district_names = sorted(DistrictNames)
    
    curr_wk_num = -1
    wk_num = int(sys.argv[2]) if len(sys.argv) > 2 else curr_wk_num
    assert wk_num == -1 or 0 < wk_num <= 53

    lang = sys.argv[3] if len(sys.argv) > 3 else 'en'
    
    # Filter the doc_infos
    doc_infos, year, wk_num = get_week_document_infos(gr_dir, 2023, wk_num)
    
    dept_doc_infos_dict = build_dept_summary(gr_dir, doc_infos)
    district_doc_infos_dict = build_district_summary(gr_dir, doc_infos)

    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    gen_archive_html(lang, env)                         
    gen_index_html(lang, env)

                         
    gen_dept_top_html(dept_names, dept_doc_infos_dict, lang, year, wk_num, env)
    gen_district_top_html(district_names, district_doc_infos_dict, lang, year, wk_num, env)    

    for (dept, doc_infos) in dept_doc_infos_dict.items():
        if doc_infos:
            gen_dept_summary_html(dept, doc_infos, lang, year, wk_num, env)

    for (district, doc_infos) in district_doc_infos_dict.items():
        if doc_infos:
            gen_district_summary_html(district, doc_infos, lang, year, wk_num, env)

    search_docs = [get_searchdoc_dict(i) for i in doc_infos]
    write_search_index(search_docs)
    
        
            
main()

"""
    def get_searchdoc_dict(self):
        doc = {}
        doc["idx"] = self.officer_idx
        doc["full_name"] = self.full_name
        doc["officer_id"] = self.officer_id
        doc["image_url"] = self.image_url
        doc["url"] = self.url
        if self.ministries:
            doc["tenure_str"] = self.tenure_str
        return doc

    def write_search_index(self):
        from lunr import lunr

        docs = [o.get_searchdoc_dict() for o in self.officer_info_dict.values()]

        lunrIdx = lunr(ref="idx", fields=["full_name", "officer_id"], documents=docs)

        search_index_file = self.output_dir / "lunr.idx.json"
        search_index_file.write_text(json.dumps(lunrIdx.serialize(), separators=(',', ':')))

        docs_file = self.output_dir / "docs.json"
        docs_file.write_text(json.dumps(docs, separators=(',', ':')))
"""
