import { Fragment, useEffect } from 'react';
import L from 'leaflet';
import {
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
  showOrigin: boolean;
  viewMode: 'desktop' | 'mobile';
  routes: EscapeRoute[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOriginChange: (origin: LatLon) => void;
}

function escapeIcon(name: string | null | undefined, selected: boolean) {
  const label = name?.trim() || 'Escape Point';
  const size = selected ? 26 : 20;
  return L.divIcon({
    className: 'escape-icon',
    html: `
      <div class="escape-pin${selected ? ' is-selected' : ''}">
        <span class="escape-pin__circle">E</span>
        ${
          selected
            ? `<span class="escape-pin__label">
                <strong>Escape Point</strong>
                <em>${escapeHtml(label)}</em>
              </span>`
            : ''
        }
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

const originIcon = L.divIcon({
  className: 'origin-icon',
  html: `
    <div class="origin-pin">
      <svg viewBox="0 0 30 40" aria-hidden="true">
        <path
          d="M15 1C7.3 1 1 7.2 1 14.8 1 25.8 15 39 15 39s14-13.2 14-24.2C29 7.2 22.7 1 15 1Z"
          fill="#cf4a4a"
          stroke="#9e3232"
          stroke-width="1.2"
        />
        <circle cx="15" cy="14.5" r="5" fill="#fffdf8" />
        <ellipse cx="10.5" cy="7.5" rx="3" ry="1.8" fill="#ffb3b3" opacity="0.5" />
      </svg>
      <span class="origin-pin__label">Tú</span>
    </div>
  `,
  iconSize: [21, 28],
  iconAnchor: [11, 26],
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

function ResizeOnViewMode({ viewMode }: { viewMode: 'desktop' | 'mobile' }) {
  const map = useMap();

  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 180);
    return () => window.clearTimeout(timer);
  }, [map, viewMode]);

  return null;
}

export function MapView({
  origin,
  showOrigin,
  viewMode,
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
      <ResizeOnViewMode viewMode={viewMode} />
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

            <Marker
              position={[route.escape_point.lat, route.escape_point.lon]}
              icon={escapeIcon(route.escape_point.name, isSelected)}
              zIndexOffset={isSelected ? 1000 : 700}
              eventHandlers={{
                click: (event) => {
                  L.DomEvent.stopPropagation(event.originalEvent);
                  onSelect(route.id);
                },
              }}
            />
          </Fragment>
        );
      })}

      {showOrigin && (
        <Marker position={[origin.lat, origin.lon]} icon={originIcon} zIndexOffset={900} />
      )}
    </MapContainer>
  );
}
