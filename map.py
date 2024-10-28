import requests
from urllib3.exceptions import HTTPError
from flask import Flask

import pandas as pd
import numpy as np

from plotly import graph_objects as go
from dash import Dash, html, dcc, Output, Input, callback, no_update, ctx

# get geojson data
try:
  r = requests.get('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json')
  r.raise_for_status()
except HTTPError as e:
  print(f'Ran into HTTPError: {e}')
counties = r.json()

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

states_df = pd.read_csv('counties_minus_alaskan.csv',
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

app = Dash(__name__)
server = app.server

# set intial app data
df = states_df[states_df['Year'] == 2020]

prev_location = ['']
cur_location = ['']

app.layout = html.Div([
  html.Div([
    html.Div([
      dcc.Dropdown(['Election Outcomes', 'Election Swing'], 'Election Outcomes', id='map-select'),
    ], id='map-select-dropdown-container', style={'display': 'inline-block', 'width': '100%'}),
    html.Div([
      dcc.Dropdown(['Voting Patterns', 'Voting Swing'], 'Voting Patterns', id='graph-select')
    ], id='graph-dropdown-container', style={'display': 'None'})
  ]),
  html.Div([
    html.Div([
      dcc.Graph(
        id='election-map', clear_on_unhover=True
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
    ], id='county-info-box', style={'width': '0', 'display': None})
  ]),
  dcc.Tooltip(id='election-hover-results'),
  html.Div(id='slider-container')
])

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
  Input('election-map', 'clickData'),
  Input('election-map-slider', 'value')
)
def select_county_info(value, _, year_range):
  if cur_location[0] == '':
    return no_update, no_update

  if value == 'Voting Patterns':
    # prepare county time series information
    location_df = states_df[states_df['ID'] == cur_location[0]]
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
    diff_df = diff[diff['ID'] == cur_location[0]]
    location_df = states_df[states_df['ID'] == cur_location[0]]
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
    Input('map-select', 'value')
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
    )
    dropdown_options = ['Voting Patterns', 'Voting Swing']
    graph_select = no_update

  return map_slider, dropdown_options, graph_select

# generate hover view
@callback(
    Output('election-hover-results', 'show'),
    Output('election-hover-results', 'bbox'),
    Output('election-hover-results', 'children'),
    Input('election-map', 'hoverData'),
    Input('county-info-box', 'style'),
    Input('map-select', 'value')
)
def display_hover_results(hover_data, style, map_select):
  if hover_data is None or style['display'] == 'inline-block':
    return False, no_update, no_update
  customdata = hover_data['points'][0]['customdata']
  bbox = hover_data['points'][0]['bbox']

  if map_select == 'Election Outcomes':
    children = [
      html.Div([
        html.B(f'{customdata[1]} County'),
        html.Br(),
        html.P('Parties', style={'fontSize':'12px', 'opacity': .8}),
        html.Hr(),
        html.Div([
          html.P(f'Democratic: {customdata[2]}%'),
          html.P(f'Republican: {customdata[3]}%')
        ])
      ])
    ]
  else:
    val = round(customdata[2] - customdata[3], 2)
    if val > 0:
      party = 'Democrats'
      opp_party = 'Republicans'
    elif val < 0:
      party = 'Republicans'
      opp_party = 'Democrats'
    else:
      party = 'Even'
    if party != 'Even':
      formatted_ele = html.P(f'{party} have gained {abs(val)} points on the {opp_party}')
    else:
      formatted_ele = html.P(f'{party}')
    children = [
      html.Div([
        html.B(f'{customdata[1]} County'),
        html.Br(),
        html.P('Swing', style={'fontSize':'12px', 'opacity': .8}),
        html.Hr(),
        html.Div([
          formatted_ele
        ])
      ])
    ]

  return True, bbox, children

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
    zmin = -25
    zmax = 25
  return cdf['ID'], customdata, z, zmin, zmax, current['colorscale']

# present the map
@callback(
  Output('election-map', 'figure'),
  Output('election-map-box', 'style'),
  Output('county-info-box', 'style'),
  Output('election-map', 'clickData'),
  Output('map-select-dropdown-container', 'style'),
  Output('graph-dropdown-container', 'style'),
  Input('election-map-slider', 'value'),
  Input('election-map', 'clickData'),
  Input('county-info-box-button', 'n_clicks'),
  Input('map-select', 'value')
)
def update_map(value, click_data, _, map_select):
  locations, customdata, z, zmin, zmax, colorscale = select_data(value, map_select)
  fig = go.Figure(go.Choroplethmapbox(geojson=counties,
                                      customdata=customdata,
                                      locations=locations,
                                      z=z,
                                      colorscale=colorscale,
                                      zmin=zmin,
                                      zmax=zmax,
                                      marker_opacity=.6,
                                      marker_line_width=.2,
                                      name='',
                                      showscale=False
                                      ))

  fig['layout']['uirevision'] = True
  fig.update_layout(mapbox_style='carto-positron',
                    mapbox_zoom=3,
                    mapbox_center={'lat': 37.0902, 'lon': -95.7129})
  fig.update_layout(margin={'r': 0, 't': 0, 'b': 0, 'l': 0})
  
  election_map_box_style = no_update
  county_info_box_style = no_update
  
  # save clicked on locations
  if click_data is not None:
    prev_location[0] = cur_location[0]
    cur_location[0] = click_data['points'][0]['location']

  # check if new county is clicked to trace, focus, and bring up info panel for county
  if prev_location[0] != cur_location[0] and ctx.triggered_id != 'county-info-box-button':
    coords = counties_df.loc[counties_df['ID'] == cur_location[0], 'COORDINATES'].values[0][0]
    lon, lat = zip(*coords)
    lon += (lon[0], )
    lat += (lat[0], )
    fig.add_trace(go.Scattermapbox(
      mode='lines',
      lat=lat,
      lon=lon,
      line={'width': 1, 'color': 'black'},
      name=cur_location[0],
    ))

    # make info panel visible
    election_map_box_style = {'display': 'inline-block', 'width': '60%'}
    county_info_box_style = {'display': 'inline-block', 'width': '40%', 'vertical-align': 'top'}
    map_select_style = {'display': 'inline-block', 'width': '60%'}
    graph_select_style = {'display': 'inline-block', 'width': '40%'}

    # set the camera location and zoom based on county clicked on
    x_max = max(lat)
    x_min = min(lat)
    y_max = max(lon)
    y_min = min(lon)
    x_diff = abs(x_max - x_min)
    y_diff = abs(y_max - y_min)
    max_diff = max(x_diff, y_diff)
    zoom = 11.5 - np.log(max_diff * 111)
    fig.update_layout(mapbox_zoom=zoom,
                      mapbox_center={'lat': x_min + (x_diff / 2), 'lon': y_min + (y_diff / 2)})

  # reset to full map view if clicking on same location
  else:
    prev_location[0] = ''
    cur_location[0] = ''
    election_map_box_style = {'display': 'inline-block', 'width': '100%'}
    county_info_box_style = {'display': 'none', 'width': '0'}
    map_select_style = {'display': 'inline-block', 'width': '100%'}
    graph_select_style = {'display': 'None'}

  fig.update_traces(hoverinfo="none", hovertemplate=None)

  return fig, election_map_box_style, county_info_box_style, None, map_select_style, graph_select_style

# app.run()
