import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { AppContextProvider } from './context/AppContext.jsx';
import './index.css';
import { captureRef } from './utils/referral';
import { captureUtm } from './utils/utm';

captureRef();
captureUtm();

ReactDOM.createRoot(document.getElementById('root')).render(
	<AppContextProvider>
		<App />
	</AppContextProvider>
);
