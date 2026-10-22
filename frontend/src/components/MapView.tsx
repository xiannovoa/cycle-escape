import { Fragment, useEffect } from 'react';
import L from 'leaflet';
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  ScaleControl,
  TileLayer,
  ZoomControl,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import type { EscapeRoute, LatLon } from '../types';
import { escapeHtml, geojsonToLatLngs, stressColor } from '../utils';

interface MapViewProps {
  origin: LatLon;
  routes: EscapeRoute[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOriginChange: (origin: LatLon) => void;
}

function escapeIcon(name: string) {
  return L.divIcon({
    className: 'escape-icon',
    html: `
      <div class="escape-marker">
        <span class="escape-marker__pulse"></span>
        <span class="escape-marker__dot"></span>
        <span class="escape-marker__label">
          <strong>Escape Point</strong>
          <em>${escapeHtml(name)}</em>
        </span>
      </div>
    `,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

const originIcon = L.divIcon({
  className: 'origin-icon',
  html: `
    <div class="origin-marker">
      <span class="origin-marker__dot"></span>
      <span class="origin-marker__label">Tú</span>
    </div>
  `,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

function MapClickHandler({ onOriginChange }: { onOriginChange: (origin: LatLon) => void }) {
  useMapEvents({
    click(event) {
      onOriginChange({ lat: event.latlng.lat, lon: event.latlng.lng });
    },
  });
  return null;
}

function FitRoutes({ routes }: { routes: EscapeRoute[] }) {
  const map = useMap();

  useEffect(() => {
    if (routes.length === 0) return;

    const coordinates = routes.flatMap((route) =>
      route.geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]),
    );
    map.fitBounds(L.latLngBounds(coordinates), {
      padding: [64, 64],
      maxZoom: 13,
    });
  }, [map, routes]);

  return null;
}

export function MapView({
  origin,
  routes,
  selectedId,
  onSelect,
  onOriginChange,
}: MapViewProps) {
  return (
    <MapContainer
      center={[origin.lat, origin.lon]}
      zoom={13}
      zoomControl={false}
      scrollWheelZoom
      className="map"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ZoomControl position="topright" />
      <ScaleControl position="bottomright" imperial={false} />
      <MapClickHandler onOriginChange={onOriginChange} />
      <FitRoutes routes={routes} />

      {routes.map((route) => (
        <Polyline
          key={`${route.id}-casing`}
          positions={geojsonToLatLngs(route.geometry)}
          interactive={false}
          pathOptions={{
            color: '#ffffff',
            weight: 11,
            opacity: route.id === selectedId ? 0.92 : 0,
            lineCap: 'round',
            lineJoin: 'round',
          }}
        />
      ))}

      {routes.map((route) => {
        const isSelected = route.id === selectedId;
        return (
          <Fragment key={route.id}>
            {route.segments.map((segment, index) => (
              <Polyline
                key={`${route.id}-${index}`}
                positions={geojsonToLatLngs(segment.geometry)}
                pathOptions={{
                  color: stressColor(segment.road_stress),
                  weight: isSelected ? 6 : 4,
                  opacity: isSelected ? 1 : 0.55,
                  dashArray: isSelected ? undefined : '6 7',
                  lineCap: 'round',
                  lineJoin: 'round',
                }}
                eventHandlers={{
                  click: (event) => {
                    L.DomEvent.stopPropagation(event.originalEvent);
                    onSelect(route.id);
                  },
                }}
              />
            ))}

            {isSelected ? (
              <Marker
                position={[route.escape_point.lat, route.escape_point.lon]}
                icon={escapeIcon(route.escape_point.name)}
                zIndexOffset={1000}
                eventHandlers={{
                  click: (event) => {
                    L.DomEvent.stopPropagation(event.originalEvent);
                  },
                }}
              />
            ) : (
              <CircleMarker
                center={[route.escape_point.lat, route.escape_point.lon]}
                radius={5}
                pathOptions={{
                  color: '#0f2e24',
                  weight: 2,
                  fillColor: '#fffdf8',
                  fillOpacity: 0.9,
                  opacity: 0.55,
                }}
                eventHandlers={{
                  click: (event) => {
                    L.DomEvent.stopPropagation(event.originalEvent);
                    onSelect(route.id);
                  },
                }}
              />
            )}
          </Fragment>
        );
      })}

      <Marker position={[origin.lat, origin.lon]} icon={originIcon} zIndexOffset={900} />
    </MapContainer>
  );
}
