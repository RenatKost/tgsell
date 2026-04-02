import Advantages from '../components/Advantages/Advantages';
import Main from '../components/Main/Main';
import Stages from '../components/Stages/Stages';
import ActivityTicker from '../components/Auction/ActivityTicker';

const Home = () => {
	return (
		<>
			<Main />
			<ActivityTicker />
			<Stages />
			<Advantages />
		</>
	);
};

export default Home;
