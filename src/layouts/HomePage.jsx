import Advantages from '../components/Advantages/Advantages';
import Main from '../components/Main/Main';
import Stages from '../components/Stages/Stages';
import ActivityTicker from '../components/Auction/ActivityTicker';

const Home = () => {
	return (
		<>
			<Main />
			<div className='max-w-7xl mx-auto px-4'>
				<ActivityTicker />
			</div>
			<Stages />
			<Advantages />
		</>
	);
};

export default Home;
