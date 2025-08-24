import React, { useState, useEffect, useRef } from 'react';
import { saveAs } from 'file-saver';

interface RecorderProps {
    data: Record<string, string | number>; // dynamic sensor data
    resolution: number; // update interval in ms
    recording: boolean;
    settings: any; // Assuming settings are passed in as a prop, or you can get it from context or store
    modules: any;  // Assuming modules are passed in as a prop, or you can get it from context or store
}

const Recorder: React.FC<RecorderProps> = ({ data, resolution, recording, settings, modules }) => {
    const [recordedData, setRecordedData] = useState<Record<string, { timestamp: string; value: number }[]>>({});
    const dataRef = useRef(data); // Reference to keep latest data
    const recordedDataRef = useRef(recordedData); // Ref to store the latest recordedData for export

    // Dynamically generate datasets for all the keys in data object
    const datasets = Object.keys(data).map((sensorLabel) => {
        const config = modules['sensorType']?.(settings); // Retrieve the configuration for each sensor type if needed
        
        return {
            label: sensorLabel, // Use the key as the label (or map it to a human-readable label if desired)
            sensorLabel, // Same as key, it's the identifier for the data
            yMin: config?.min_value ?? -Infinity, // Provide default min/max if not available
            yMax: config?.max_value ?? Infinity,
        };
    });

    // Update data ref to avoid stale closure
    useEffect(() => {
        dataRef.current = data;
    }, [data]);

    // Recording logic
    useEffect(() => {
        let interval: NodeJS.Timeout | null = null;

        if (recording) {
            interval = setInterval(() => {
                const timestamp = new Date().toISOString();

                setRecordedData(prevData => {
                    const updated = { ...prevData };

                    datasets.forEach(({ label, sensorLabel, yMin, yMax }) => {
                        const value = dataRef.current[sensorLabel]; // Get the value from data using sensorLabel
                        const numValue = isNaN(Number(value)) ? 0 : Math.max(yMin, Math.min(Number(value), yMax)); // Ensure value is within yMin and yMax

                        if (!updated[label]) updated[label] = []; // Initialize an empty array for each label
                        updated[label].push({ timestamp, value: numValue });
                    });

                    // Update the ref with the latest data for export
                    recordedDataRef.current = updated;
                    return updated;
                });
            }, resolution);
        } else {
            if (interval) {
                clearInterval(interval); // Stop recording when recording is false
                exportData(); // Export the data when stopping the recording
            }
        }

        // Cleanup on component unmount or when recording stops
        return () => {
            if (interval) {
                clearInterval(interval);
                exportData(); // Export data if it's unmounted or recording stops
            }
        };
    }, [recording, resolution, settings, modules]);

    const exportData = () => {
        const date = new Date();
        const timestamp = date.toISOString().replace(/[-:T.]/g, '_');

        // Use the ref value for recordedData to export the latest data
        const exportObj = Object.keys(recordedDataRef.current).map((label) => {
            return {
                label,
                data: recordedDataRef.current[label]?.map((entry) => ({
                    timestamp: entry.timestamp,
                    value: entry.value,
                })) || [],
            };
        });

        const blob = new Blob([JSON.stringify(exportObj, null, 2)], { type: 'application/json' });
        saveAs(blob, `V-Link_Recording_${timestamp}.json`);
    };

    return null;
};

export default Recorder;
