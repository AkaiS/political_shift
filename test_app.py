import copy
import json
import unittest

from map import app, server, COUNTIES_URL


def find_component(node, component_id):
    if isinstance(node, dict):
        if node.get('props', {}).get('id') == component_id:
            return node['props']
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = find_component(child, component_id)
        if found is not None:
            return found


class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = server.test_client()
        self.client.get('/')
        self.layout = self.client.get('/_dash-layout').json

    def apply_map_update(self, response, figure=None):
        figure = copy.deepcopy(figure or find_component(self.layout, 'election-map')['figure'])
        for change in response['election-map']['figure']['operations']:
            self.assertEqual(change['operation'], 'Assign')
            target = figure
            for part in change['location'][:-1]:
                target = target[part]
            target[change['location'][-1]] = change['params']['value']
        return figure

    def callback(self, component, values, changed, state=None):
        key, spec = next(
            (key, spec) for key, spec in app.callback_map.items()
            if any(output.component_id == component for output in spec['output'])
        )
        payload = {
            'output': key,
            'outputs': [
                {'id': output.component_id, 'property': output.component_property}
                for output in spec['output']
            ],
            'inputs': [dict(item, value=value) for item, value in zip(spec['inputs'], values)],
            'state': [dict(item, value=value) for item, value in zip(spec['state'], state or [])],
            'changedPropIds': [changed],
        }
        response = self.client.post('/_dash-update-component', json=payload)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json['response']

    def update_map(self, selection=None, click=None, changed='election-map-slider.value', year=2020, mode='Election Outcomes'):
        return self.callback(
            'election-map', [year, click, 0], changed, [mode, selection]
        )

    def test_map_interactions_do_not_resend_county_geometry(self):
        for kwargs, budget in [
            ({'year': 2016}, 250_000),
            ({'year': [2000, 2020], 'mode': 'Election Swing'}, 500_000),
            ({'click': {'points': [{'location': '01001'}]}, 'changed': 'election-map.clickData'}, 10_000),
            ({'selection': '01001', 'changed': 'county-info-box-button.n_clicks'}, 10_000),
        ]:
            with self.subTest(kwargs=kwargs):
                response = json.dumps(self.update_map(**kwargs))
                self.assertLess(len(response.encode()), budget)
                self.assertNotIn('geojson', response)

    def test_slider_exists_in_initial_layout(self):
        slider = find_component(self.layout, 'election-map-slider')
        self.assertEqual(slider['value'], 2000)
        graph_options = find_component(self.layout, 'graph-select')['options']
        self.assertTrue(next(option for option in graph_options if option['value'] == 'Voting Swing')['disabled'])

    def test_hover_does_not_require_server_callbacks(self):
        for spec in app.callback_map.values():
            self.assertNotIn({'id': 'election-map', 'property': 'hoverData'}, spec['inputs'])

    def test_routes_and_initial_map(self):
        for path in ['/', '/healthz', '/_dash-layout', '/_dash-dependencies']:
            self.assertEqual(self.client.get(path).status_code, 200)
        initial = find_component(self.layout, 'election-map')['figure']
        self.assertEqual(initial['data'][0]['geojson'], COUNTIES_URL)
        self.assertGreater(len(initial['data'][0]['locations']), 3000)
        self.assertIn('Democratic:', initial['data'][0]['hovertemplate'])
        result = self.update_map()
        figure = self.apply_map_update(result)
        self.assertGreater(len(figure['data'][0]['locations']), 3000)
        self.assertEqual(figure['layout']['mapbox']['style'], 'open-street-map')
        self.assertNotEqual(figure['data'][0]['z'], initial['data'][0]['z'])
        self.assertIsNone(result['selected-county']['data'])
        result = self.update_map(year=[2000, 2020], mode='Election Swing')
        figure = self.apply_map_update(result, figure)
        self.assertGreater(len(figure['data'][0]['locations']), 3000)
        self.assertEqual(figure['layout']['mapbox']['style'], 'open-street-map')
        self.assertIn('customdata[4]', figure['data'][0]['hovertemplate'])
        self.assertEqual(len(figure['data'][0]['customdata'][0]), 5)

    def test_geometry_is_cacheable_and_supports_conditional_requests(self):
        response = self.client.get(COUNTIES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(json.loads(response.data)['features']), 3000)
        self.assertIn('immutable', response.headers['Cache-Control'])
        self.assertIn('max-age=31536000', response.headers['Cache-Control'])
        cached = self.client.get(COUNTIES_URL, headers={'If-None-Match': response.headers['ETag']})
        self.assertEqual(cached.status_code, 304)

    def test_county_selection_is_per_browser_and_survives_year_change(self):
        click = {'points': [{'location': '01001'}]}
        first = self.update_map(click=click, changed='election-map.clickData')
        self.assertEqual(first['selected-county']['data'], '01001')
        selected = self.apply_map_update(first)
        self.assertGreater(len(selected['data'][1]['lat']), 0)
        self.assertIsNone(selected['data'][0]['hovertemplate'])
        self.assertEqual(selected['data'][0]['hoverinfo'], 'none')
        second = self.update_map()
        self.assertIsNone(second['selected-county']['data'])
        preserved = self.update_map(selection='01001', year=2016)
        self.assertEqual(preserved['selected-county']['data'], '01001')
        self.assertFalse(any(operation['location'][:2] == ['layout', 'mapbox']
                             for operation in preserved['election-map']['figure']['operations']))
        closed = self.update_map(selection='01001', changed='county-info-box-button.n_clicks')
        self.assertIsNone(closed['selected-county']['data'])
        deselected = self.apply_map_update(closed, selected)
        self.assertEqual(deselected['data'][1]['lat'], [])
        self.assertEqual(deselected['layout']['mapbox']['zoom'], 3)
        self.assertIn('Democratic:', deselected['data'][0]['hovertemplate'])
        toggled = self.update_map(selection='01001', click=click, changed='election-map.clickData')
        self.assertIsNone(toggled['selected-county']['data'])

    def test_selected_county_graphs_and_multipolygon(self):
        for graph, years in [('Voting Patterns', 2020), ('Voting Swing', [2000, 2020])]:
            result = self.callback('location-name', [graph, '01001', years], 'selected-county.data')
            self.assertEqual(result['location-name']['children'], 'Autauga County')
        result = self.update_map(click={'points': [{'location': '06075'}]}, changed='election-map.clickData')
        self.assertEqual(result['selected-county']['data'], '06075')


if __name__ == '__main__':
    unittest.main()
