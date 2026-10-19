import unittest

from map import app, server


class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = server.test_client()
        self.client.get('/')

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
            'election-map', [year, click, 0, mode], changed, [selection]
        )

    def test_routes_and_initial_map(self):
        for path in ['/', '/healthz', '/_dash-layout', '/_dash-dependencies']:
            self.assertEqual(self.client.get(path).status_code, 200)
        result = self.update_map()
        self.assertGreater(len(result['election-map']['figure']['data'][0]['locations']), 3000)
        self.assertEqual(result['election-map']['figure']['layout']['mapbox']['style'], 'open-street-map')
        self.assertIsNone(result['selected-county']['data'])
        result = self.update_map(year=[2000, 2020], mode='Election Swing')
        self.assertGreater(len(result['election-map']['figure']['data'][0]['locations']), 3000)
        self.assertEqual(result['election-map']['figure']['layout']['mapbox']['style'], 'open-street-map')

    def test_county_selection_is_per_browser_and_survives_year_change(self):
        click = {'points': [{'location': '01001'}]}
        first = self.update_map(click=click, changed='election-map.clickData')
        self.assertEqual(first['selected-county']['data'], '01001')
        second = self.update_map()
        self.assertIsNone(second['selected-county']['data'])
        preserved = self.update_map(selection='01001', year=2016)
        self.assertEqual(preserved['selected-county']['data'], '01001')
        closed = self.update_map(selection='01001', changed='county-info-box-button.n_clicks')
        self.assertIsNone(closed['selected-county']['data'])
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
