import { useEffect, useRef } from 'react';
import styled, { useTheme } from 'styled-components';

import LinearGauge from './../../../components/LinearGauge';
import DataList from '../../../components/DataList'

import { APP } from '../../../../store/Store';

const Container = styled.div`
  display: flex;
  flex-direction:column;
  gap: 30px;
  width: 100%;
  height: 100%;
`;

const Gauge = styled.div`
  height: 60%;
  width: 100%;
  gap: 20px;
`;

const List = styled.div`
  width: 100%;
  gap: 20px;
`;

const Race = () => {
	const app = APP((state) => state);

	const Datalist = DataList(app.settings.dash_race, 6, 2) // Amount of Items, 2 Columns

	const renderStartTime = useRef(0);

	// Record start time right before the render happens
	renderStartTime.current = performance.now();

	useEffect(() => {
		const renderEndTime = performance.now();
		const renderDuration = renderEndTime - renderStartTime.current;
		
		//console.log(`[Race.tsx] Re-render duration: ${renderDuration.toFixed(2)}ms`);

		// This effect runs *after* the component renders, giving us the true render latency.
		// It depends on `app.system.lastUpdate`, which is set from the worker's timestamp.
		if (app.system.lastUpdate) {
			const renderLatency = Date.now() - app.system.lastUpdate;
			//console.log(`Server - Render Latency: ${renderLatency}ms`);
		}
	}, [app.system.lastUpdate]);

	return (
		<Container>
			<Gauge>
				<LinearGauge />
			</Gauge>
			<List>
				{Datalist}
			</List>
		</Container>
	)
};


export default Race;