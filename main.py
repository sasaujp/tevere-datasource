import click
from SPARQLWrapper import SPARQLWrapper
import json
from itertools import count
import os
from time import sleep
from logging import getLogger
import glob
import shutil
from collections import defaultdict
import logging
from datetime import date


logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')
logger = getLogger()

LIMIT = 10000

@click.group()
def main():
    pass

@main.command()
@click.option('--queries', default='queries')
@click.option('--query', default=None)
def fetch(queries, query):
    logger.debug('%s, %s', queries, query)
    # logger.debug('%s', glob.glob1(queries, '*.rq'))

    if not query:
        if os.path.exists('dist'):
            shutil.rmtree('dist')
    if not os.path.exists('dist'):
        os.mkdir('dist')

    if not query:
        query_files = list(filter(lambda x: x.endswith('.rq'), glob.glob('queries/**', recursive=True)))
    else:
        query_files = [query]
    for query_file in query_files:
        endpoint = query_file.split('/')[-2]
        service = SPARQLWrapper(
            endpoint=f'http://{endpoint}/sparql',
            returnFormat='json')
        filename, _ = os.path.splitext(os.path.basename(query_file))
        original_query = open(query_file).read()
        for c in count(0):
            query_string = original_query + f'offset {c * LIMIT}\n limit {LIMIT}'
            service.setQuery(query_string)
            results = service.query().convert()
            number_of_bindings = len(results['results']['bindings'])
            logger.info('number of bindings...> %s', number_of_bindings)
            if number_of_bindings == 0:
                break
            os.makedirs(os.path.join('dist', endpoint), exist_ok=True)
            data_file_name = os.path.join('dist', endpoint, f'{filename}_{c}.json')
            logger.info('writing...> %s', data_file_name)
            json.dump(
                results,
                open(data_file_name, 'w'),
                indent=2,
                ensure_ascii=False)
            if number_of_bindings == LIMIT:
                sleep(5)
                continue
            break


class keydefaultdict(defaultdict):
    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        else:
            ret = self[key] = self.default_factory(key)
            return ret


@main.command()
@click.argument('dirpath')
@click.option('--data_path', default='data')
def make_data(dirpath, data_path):
    def default_factory1():
        return keydefaultdict(default_factory2)

    def default_factory2(key):
        if key in ('label', 'abstract'):
            return {}
        return []

    if os.path.exists(data_path):
        shutil.rmtree(data_path)
    os.mkdir(data_path)

    redirects = {}
    for json_file in filter(lambda x: 'redirect' in x, glob.glob1(os.path.join(dirpath, 'dbpedia.org'), '*.json')):
        json_file = os.path.join(dirpath, 'dbpedia.org', json_file)
        data = json.load(open(json_file))
        bindings = data['results']['bindings']
        for row in bindings:
            redirect = row['redirect']
            key = list(filter(lambda x: not x == 'redirect', row.keys()))[0]
            redirects[redirect['value']] = row[key]['value']

    def get_redirect(value):
        if value in redirects:
            logger.debug('%s -> %s', value, redirects[value])
        return redirects.get(value, value)

    battles = defaultdict(default_factory1)
    commanders = defaultdict(default_factory1)
    subjects = defaultdict(default_factory1)
    places = defaultdict(default_factory1)
    for json_file in filter(lambda x: 'redirect' not in x, glob.glob1(os.path.join(dirpath, 'dbpedia.org'), '*.json')):
        json_file = os.path.join(dirpath, 'dbpedia.org', json_file)
        data = json.load(open(json_file))
        bindings = data['results']['bindings']
        logger.debug('%s', json_file)
        for row in bindings:
            if 'battle' in row:
                battle = row['battle']
                key = list(filter(lambda x: not x == 'battle', row.keys()))
                if not key:
                    continue
                key = key[0]
                if key in ('label', 'abstract'):
                    lang = row[key]['xml:lang']
                    battles[get_redirect(battle['value'])][key][lang] = row[key]['value']
                else:
                    battles[get_redirect(battle['value'])][key].append(get_redirect(row[key]['value']))
            if 'commander' in row:
                commander = row['commander']
                key = list(filter(lambda x: not x == 'commander', row.keys()))[0]
                if key in ('label', 'abstract'):
                    lang = row[key]['xml:lang']
                    commanders[get_redirect(commander['value'])][key][lang] = row[key]['value']
                else:
                    commanders[get_redirect(commander['value'])][key].append(row[key]['value'])
            if 'subject' in row:
                subject = row['subject']
                key = list(filter(lambda x: not x == 'subject', row.keys()))[0]
                if key in ('label', 'abstract'):
                    lang = row[key]['xml:lang']
                    subjects[subject['value']][key][lang] = row[key]['value']
                else:
                    subjects[subject['value']][key].append(get_redirect(row[key]['value']))
            if 'place' in row:
                place = row['place']
                key = list(filter(lambda x: not x == 'place', row.keys()))[0]
                if key == 'point':
                    places[get_redirect(place['value'])][key].append(row[key]['value'])
                elif key in ('lat', 'long'):
                    places[get_redirect(place['value'])]['point'].append(f"{row['lat']['value']} {row['long']['value']}")
                if key in ('label',):
                    lang = row[key]['xml:lang']
                    places[get_redirect(place['value'])][key][lang] = row[key]['value']
    wikidata_dates = defaultdict(set)
    for json_file in glob.glob1(os.path.join(dirpath, 'wikidata.dbpedia.org'), '*.json'):
        json_file = os.path.join(dirpath, 'wikidata.dbpedia.org', json_file)
        data = json.load(open(json_file))
        bindings = data['results']['bindings']
        logger.debug('%s', json_file)
        for row in bindings:
            battle = row['battle']['value']
            date = row['date']['value']
            wikidata_dates[battle].add(date)
            logger.debug('%s, %s', battle, date)
    for uri, battle in battles.items():
        sameAs = battle['sameAs']
        del battle['sameAs']
        for sameURI in sameAs:
            if sameURI in wikidata_dates:
                wikidata_date = wikidata_dates[sameURI]
                break
        else:
            continue
        wikidata_date = [d.split('+')[0] for d in wikidata_date]
        logger.debug('%s, %s: %s -> %s', uri, battle.get('point'), battle['date'], wikidata_date)
        battle['date'] = wikidata_date

    json.dump(
        battles,
        open(os.path.join(data_path, 'battles.json'), 'w'),
        indent=2,
        ensure_ascii=False)
    json.dump(
        commanders,
        open(os.path.join(data_path, 'commanders.json'), 'w'),
        indent=2,
        ensure_ascii=False)
    json.dump(
        subjects,
        open(os.path.join(data_path, 'subjects.json'), 'w'),
        indent=2,
        ensure_ascii=False)
    json.dump(
        places,
        open(os.path.join(data_path, 'places.json'), 'w'),
        indent=2,
        ensure_ascii=False)



@main.command()
@click.argument('battles')
def analysis(battles):
    data = json.load(open(battles))
    logger.info('battles: %s', len(data))


def interpretation_date_property(date_property):
    if 'century' in date_property.lower():
        return None
    if date_property.startswith('--'):
        return None
    this_year = date.today().year
    try:
        y, m, n = [int(i)for i in date_property.rsplit('-', 2)]
        if y > this_year:
            raise
        return y, m, n
    except:
        pass

    try:
        y = int(date_property)
        if y > this_year:
            raise
        return y, None, None
    except:
        pass

    import re
    m = re.search(r'\D*([0-9]+)\D*', date_property)
    if m:
        groups = m.groups()
        y = groups[0]
        y = int(y)
        if 'BC' in date_property or 'B.C' in date_property:
            return -y
        if not y > this_year:
            return y, None, None


if __name__ == '__main__':
    main()
