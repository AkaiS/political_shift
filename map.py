import hashlib
import json
from pathlib import Path

import pandas as pd
import numpy as np

from plotly import graph_objects as go
from dash import Dash, html, dcc, Output, Input, State, Patch, callback, no_update, ctx
from flask import send_file

DATA_DIR = Path(__file__).resolve().parent
COUNTIES_FILE = DATA_DIR / 'counties.geojson'
COUNTIES_VERSION = hashlib.sha256(COUNTIES_FILE.read_bytes()).hexdigest()[:16]
COUNTIES_URL = f'/data/counties-{COUNTIES_VERSION}.geojson'
with COUNTIES_FILE.open() as source:
  counties = json.load(source)

# format state and county info to match ID found in state_df
counties_df = pd.DataFrame({**lo['properties'],
                            'COORDINATES': lo['geometry']['coordinates']}
                            for lo in counties['features'])
counties_df['ID'] = counties_df['STATE'] + counties_df['COUNTY']
counties_df

#
# counties_geometry = pd.DataFrame({'id': lo['id'], 'coordinates': lo['geometry']['coordinates']} for lo in counties['features'])
# counties_geometry = counties_geometry.set_index('id')
# counties_geometry.index.name = None

# import particular cols from states_df
import_cols = [('County',	''),
  ('Republican', '#'),
  ('Republican', '%'),
  ('Democratic', '#'),
  ('Democratic', '%'),
  ('Total', ''),
  ('Year', ''),
  ('State', ''),
  ('FIPS', ''),
  ('ID', ''),
]

states_df = pd.read_csv(DATA_DIR / 'counties_minus_alaskan.csv',
                        index_col=0,
                        skiprows=2,
                        names=import_cols,
                        dtype={('FIPS',''): object,('ID',''): object})

# narrow comparison cols to quantitative data categories
quant_cols = [
('Republican', '#'),
('Republican', '%'),
('Democratic', '#'),
('Democratic', '%'),
( 'Total', '')]

# find the difference between cols to quantify changes between elections
diff = states_df.groupby(by='ID')[quant_cols].diff().fillna(0)
diff['ID'], diff['Year'] = states_df['ID'], states_df['Year']

# add county name to diff dataframe
da_map = pd.Series(states_df['County'].values, index=states_df['ID'])
da_map = da_map[~da_map.index.duplicated(keep='first')]
diff['County'] = diff['ID'].map(da_map)

app = Dash(__name__, title='Political Shift', suppress_callback_exceptions=True)
server = app.server

@server.get(COUNTIES_URL)
def county_geometry():
  response = send_file(COUNTIES_FILE, mimetype='application/geo+json',
                       max_age=31536000, etag=COUNTIES_VERSION, conditional=True)
  response.cache_control.immutable = True
  return response


@server.get('/healthz')
def healthz():
  return {'status': 'ok'}

# set datasets for different maps
map_select_data = {
  'Election Outcomes': {
    'df': states_df,
    'colorscale': 'Bluered_r',
  },
  'Election Swing': {
    'df': diff,
    'colorscale': 'Picnic_r',
  }
}

# generate graphs and info to be presented alongside map
@callback(
  Output('location-name', 'children'),
  Output('county-info-body', 'children'),
  Input('graph-select', 'value'),
  Input('selected-county', 'data'),
  Input('election-map-slider', 'value')
)
def select_county_info(value, selected_county, year_range):
  if not selected_county:
    return no_update, no_update

  if value == 'Voting Patterns':
    # prepare county time series information
    location_df = states_df[states_df['ID'] == selected_county]
    county = location_df['County'].values[0]
    location_name = f'{county} County'
    third_party = 100 - (location_df[('Democratic', '%')] + location_df[('Republican', '%')])

    # draw county time series
    info_fig = go.Figure()
    info_fig.add_trace(go.Scatter(
      x=location_df['Year'].sort_values(),
      y=location_df[('Democratic', '%')],
      connectgaps=True,
      name='Democratic'
      )
    )
    info_fig.add_trace(go.Scatter(
      x=location_df['Year'].sort_values(),
      y=location_df[('Republican', '%')],
      connectgaps=True,
      name='Republican'
      )
    )
    info_fig.add_trace(go.Scatter(
      x=location_df['Year'].sort_values(),
      y=third_party,
      connectgaps=True,
      name='Other'
      )
    )
    info_fig.update_layout(hovermode='x unified',
                          showlegend=False,
                          margin={'r': 0, 't': 20, 'b': 0, 'l': 5},
                          yaxis_range=[0, 100],
                          height=405)
    info_fig.update_xaxes(tickvals=location_df['Year'].sort_values())
    info_fig.update_yaxes(tickvals=list(range(0, 101, 20)))
    body = dcc.Graph(figure=info_fig)

  if value == 'Voting Swing':
    if not isinstance(year_range, list):
      year_range = [2000, 2020]
    diff_df = diff[diff['ID'] == selected_county]
    location_df = states_df[states_df['ID'] == selected_county]
    location_df = location_df[location_df['Year'] == year_range[1]]
    diff_df = diff_df[(diff_df['Year'] > year_range[0]) & (diff_df['Year'] <= year_range[1])]
    county = diff_df['County'].values[0]
    location_name = f'{county} County'
    agg_diff_df = diff_df.groupby('ID').agg({
      ('Republican', '#'): 'sum',
      ('Republican', '%'): 'sum',
      ('Democratic', '#'): 'sum',
      ('Democratic', '%'): 'sum',
      (     'Total',  ''): 'sum',
      (    'County',  ''): 'first'
    }).reset_index()
    
    swing_pct = round((agg_diff_df[('Democratic', '%')] - agg_diff_df[('Republican', '%')]).values[0], 2)
    vote_adv = (location_df[('Democratic', '#')] - location_df[('Republican', '#')]).values[0]
    swing_adv_party = ''

    if swing_pct > 0:
      swing_adv_party = 'Democratic'
      swing_disadv_party = 'Republican'
    elif swing_pct < 0:
      swing_adv_party = 'Republican'
      swing_disadv_party = 'Democratic'
    
    if vote_adv > 0:
      total_adv_party = 'Democratic'
      total_disadv_party = 'Republican'
    elif vote_adv < 0:
      total_adv_party = 'Republican'
      total_disadv_party = 'Democratic'


    if swing_pct == 0:
      swing_string = f'Neither party gained points.'
    else:
      swing_string = f'The {swing_adv_party} party gained {abs(swing_pct)} points over the\
      {swing_disadv_party} party from {year_range[0]} to {year_range[1]}.'

    advantage_total = (location_df[(total_adv_party, '#')] - location_df[(total_disadv_party, '#')]).values[0]
    swing_total = (agg_diff_df[(total_adv_party, '#')] - agg_diff_df[(total_disadv_party, '#')]).values[0]

    total_votes = location_df[('Total', '')].values[0]
    vote_delta = agg_diff_df[('Total', '')].values[0]

    # style col headings
    current_year_string = f'In {year_range[1]}'
    starting_year_string = f'Change Since {year_range[0]}'

    # style change data
    vote_delta = f'+{vote_delta}' if vote_delta > 0 else f'{vote_delta}'
    swing_total = f'+{swing_total}' if swing_total > 0 else f'{swing_total}'

    # make class styles to remove inline css
    body = html.Div([
      html.Div([swing_string], style={'padding': '0 8px 0 8px'}),
      html.Div([
        html.Table([
          html.Thead([
            html.Th(),
            html.Th(current_year_string, style={'padding': '0 0 5px 10px'}),
            html.Th(starting_year_string, style={'padding': '0 0 5px 20px'}),
          ], style={'text-align': 'right'}),
          html.Tbody([
            html.Tr([
              html.Th('Total Voters'),
              html.Td(total_votes, style={'padding': '8px 0 8px 0'}),
              html.Td(vote_delta)
            ], style={'border-bottom': '1px solid #cccccc'}),
            html.Tr([
              html.Th(f'{total_adv_party} Party Advantage'),
              html.Td(advantage_total, style={'padding': '8px 0 8px 0'}),
              html.Td(swing_total)
            ], style={'border-bottom': '1px solid #cccccc', })
          ], style={'text-align': 'right'})
        ], style={'border-collapse': 'collapse', 'margin': '8px'})
      ], style={'width': '100%'})
    ], style={'width': '100%', 'height': '405px', 'background-color': 'white'})


  return location_name, body

# set slider relative to map chosen
@callback(
    Output('slider-container', 'children'),
    Output('graph-select', 'options'),
    Output('graph-select', 'value'),
    Input('map-select', 'value'),
    prevent_initial_call=True,
)
def select_map(value):
  if value == 'Election Outcomes':
    map_slider = dcc.Slider(
      states_df['Year'].min(),
      states_df['Year'].max(),
      step=4,
      id='election-map-slider',
      marks={str(year): str(year) for year in states_df['Year'].unique()},
      value=2000,
      included=False,
    )
    dropdown_options = [
      {'label': 'Voting Patterns', 'value': 'Voting Patterns'},
      {'label': 'Voting Swing (Swap to Election Swing Map)', 'value': 'Voting Swing', 'disabled': True}
    ]
    graph_select = 'Voting Patterns'

  elif value == 'Election Swing':
    map_slider = dcc.RangeSlider(
      states_df['Year'].min(),
      states_df['Year'].max(),
      step=4,
      id='election-map-slider',
      marks={str(year): str(year) for year in states_df['Year'].unique()},
      value=[2000, 2020],
      allowCross=False,
      pushable=4,
    )
    dropdown_options = ['Voting Patterns', 'Voting Swing']
    graph_select = no_update

  return map_slider, dropdown_options, graph_select

# Plotly renders hover labels locally using the data already in the figure.
OUTCOME_HOVER = ('<b>%{customdata[1]} County</b><br>'
                 'Democratic: %{customdata[2]}%<br>'
                 'Republican: %{customdata[3]}%<extra></extra>')
SWING_HOVER = '<b>%{customdata[1]} County</b><br>%{customdata[4]}<extra></extra>'


def swing_label(value):
  value = round(value, 2)
  if value == 0:
    return 'Even'
  party, opponent = ('Democrats', 'Republicans') if value > 0 else ('Republicans', 'Democrats')
  return f'{party} have gained {abs(value)} points on the {opponent}'


# filter data relative to map and year(s) chosen
def select_data(value, map_select):
  current = map_select_data[map_select]
  cdf = current['df']
  if map_select == 'Election Outcomes':
    # ugly af solution, indirect method of checking whether value comes from Slider or RangeSlider
    if type(value) == list:
      value = 2000
    cdf = cdf[cdf['Year'] == value]
    customdata = pd.concat([cdf['ID'], cdf[('County', '')], cdf[('Democratic', '%')], cdf[('Republican', '%')]], axis=1)
    z = cdf[('Democratic', '%')] - cdf[('Republican', '%')]
    zmin = -50
    zmax = 50
  else:
    if type(value) == int:
      value = [2000, 2020]
    cdf = cdf[(cdf['Year'] > value[0]) & (cdf['Year'] <= value[1])]
    cdf = cdf.groupby('ID').agg({
      ('Republican', '#'): 'sum',
      ('Republican', '%'): 'sum',
      ('Democratic', '#'): 'sum',
      ('Democratic', '%'): 'sum',
      (     'Total',  ''): 'sum',
      (    'County',  ''): 'first'
    }).reset_index()
    customdata = pd.concat([cdf['ID'], cdf[('County', '')], cdf[('Democratic', '%')], cdf[('Republican', '%')]], axis=1)
    z = cdf[('Democratic', '%')] - cdf[('Republican', '%')]
    customdata['swing_label'] = [swing_label(value) for value in z]
    zmin = -25
    zmax = 25
  return cdf['ID'], customdata, z, zmin, zmax, current['colorscale']

def initial_map():
  locations, customdata, z, zmin, zmax, colorscale = select_data(2000, 'Election Outcomes')
  fig = go.Figure(go.Choroplethmapbox(
    geojson=COUNTIES_URL,
    customdata=customdata.to_numpy().tolist(),
    locations=locations.tolist(),
    z=z.tolist(),
    colorscale=colorscale,
    zmin=zmin,
    zmax=zmax,
    marker_opacity=.6,
    marker_line_width=.2,
    name='',
    showscale=False,
    hovertemplate=OUTCOME_HOVER,
  ))
  # Keep a separate trace for selection so county clicks never replace the map.
  fig.add_trace(go.Scattermapbox(
    mode='lines', lat=[], lon=[], line={'width': 1, 'color': 'black'},
    hoverinfo='skip', showlegend=False,
  ))
  fig.update_layout(
    uirevision=True,
    mapbox_style='open-street-map',
    mapbox_zoom=3,
    mapbox_center={'lat': 37.0902, 'lon': -95.7129},
    margin={'r': 0, 't': 0, 'b': 0, 'l': 0},
    showlegend=False,
  )
  return fig


# Update only the values that changed; the browser retains geometry and traces.
@callback(
  Output('election-map', 'figure'),
  Output('election-map-box', 'style'),
  Output('county-info-box', 'style'),
  Output('election-map', 'clickData'),
  Output('map-select-dropdown-container', 'style'),
  Output('graph-dropdown-container', 'style'),
  Output('selected-county', 'data'),
  Input('election-map-slider', 'value'),
  Input('election-map', 'clickData'),
  Input('county-info-box-button', 'n_clicks'),
  State('map-select', 'value'),
  State('selected-county', 'data'),
  prevent_initial_call=True,
)
def update_map(value, click_data, _, map_select, selected_county):
  fig = Patch()
  if ctx.triggered_id == 'election-map-slider':
    locations, customdata, z, zmin, zmax, colorscale = select_data(value, map_select)
    fig['data'][0]['locations'] = locations.tolist()
    fig['data'][0]['customdata'] = customdata.to_numpy().tolist()
    fig['data'][0]['z'] = z.tolist()
    fig['data'][0]['zmin'] = zmin
    fig['data'][0]['zmax'] = zmax
    fig['data'][0]['colorscale'] = go.Choroplethmapbox(colorscale=colorscale).colorscale

  if ctx.triggered_id == 'county-info-box-button':
    selected_county = None
  elif ctx.triggered_id == 'election-map' and click_data is not None:
    clicked_county = click_data['points'][0]['location']
    selected_county = None if clicked_county == selected_county else clicked_county

  # check if new county is clicked to trace, focus, and bring up info panel for county
  if selected_county:
    # make info panel visible
    election_map_box_style = {'display': 'inline-block', 'width': '60%'}
    county_info_box_style = {'display': 'inline-block', 'width': '40%', 'vertical-align': 'top'}
    map_select_style = {'display': 'inline-block', 'width': '60%'}
    graph_select_style = {'display': 'inline-block', 'width': '40%'}

    if ctx.triggered_id == 'election-map':
      coords = counties_df.loc[counties_df['ID'] == selected_county, 'COORDINATES'].values[0][0]
      while isinstance(coords[0][0], list):
        coords = coords[0]
      lon, lat = zip(*coords)
      lon += (lon[0], )
      lat += (lat[0], )
      fig['data'][1]['lat'] = lat
      fig['data'][1]['lon'] = lon
      fig['data'][1]['name'] = selected_county

      # Focus the selected county only on a click, preserving pans on year changes.
      x_min, x_max = min(lat), max(lat)
      y_min, y_max = min(lon), max(lon)
      x_diff, y_diff = x_max - x_min, y_max - y_min
      fig['layout']['mapbox']['zoom'] = 11.5 - np.log(max(x_diff, y_diff) * 111)
      fig['layout']['mapbox']['center'] = {'lat': x_min + (x_diff / 2), 'lon': y_min + (y_diff / 2)}

  # reset to full map view if clicking on same location
  else:
    fig['data'][1]['lat'] = []
    fig['data'][1]['lon'] = []
    if ctx.triggered_id in ('election-map', 'county-info-box-button'):
      fig['layout']['mapbox']['zoom'] = 3
      fig['layout']['mapbox']['center'] = {'lat': 37.0902, 'lon': -95.7129}
    election_map_box_style = {'display': 'inline-block', 'width': '100%'}
    county_info_box_style = {'display': 'none', 'width': '0'}
    map_select_style = {'display': 'inline-block', 'width': '100%'}
    graph_select_style = {'display': 'None'}

  fig['data'][0]['hoverinfo'] = 'none' if selected_county else 'all'
  fig['data'][0]['hovertemplate'] = None if selected_county else (
    OUTCOME_HOVER if map_select == 'Election Outcomes' else SWING_HOVER
  )

  return fig, election_map_box_style, county_info_box_style, None, map_select_style, graph_select_style, selected_county

app.layout = html.Div([
  dcc.Store(id='selected-county'),
  html.Div([
    html.Div([
      dcc.Dropdown(['Election Outcomes', 'Election Swing'], 'Election Outcomes', id='map-select'),
    ], id='map-select-dropdown-container', style={'display': 'inline-block', 'width': '100%'}),
    html.Div([
      dcc.Dropdown(select_map('Election Outcomes')[1], 'Voting Patterns', id='graph-select')
    ], id='graph-dropdown-container', style={'display': 'None'})
  ]),
  html.Div([
    html.Div([
      dcc.Graph(
        id='election-map', figure=initial_map()
      ),
    ], id='election-map-box', style={'width': '100%'}),
    html.Div([
        html.Div([
          html.H4(id='location-name', style={'display': 'inline-block', 'margin-left': '8px'}),
          html.Button(id='county-info-box-button',
                      children='Close Graph',
                      style={'display': 'inline-block',
                             'margin-right': '8px'}
                      )
          ],
          style={'height': '45px',
                 'display': 'flex',
                 'justify-content': 'space-between',
                 'background': 'white',
                 'text-align': 'center',
                 'align-items': 'center'}
        ),
        html.Div(id='county-info-body')
    ], id='county-info-box', style={'width': '0', 'display': 'none'})
  ]),
  html.Div(select_map('Election Outcomes')[0], id='slider-container')
])
