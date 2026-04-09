import NavBar from '../sections/NavBar';
import Hero from '../sections/Hero';
import HowItWorks from '../sections/HowItWorks';
import Simulation from '../sections/Simulation';
import AppScreen from '../sections/AppScreen';
import Pricing from '../sections/Pricing';
import Footer from '../sections/Footer';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import EnergyField from '../components/effects/EnergyField';
import { useApp } from '../context/AppContext';

export default function Landing() {
  const { activeCategory } = useApp();
  return (
    <div data-category={activeCategory} className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar />
      <main className="relative">
        <MeshGradientBg />
        <EnergyField />
        <Hero />
        <HowItWorks />
        <Simulation />
        <AppScreen />
        <Pricing />
      </main>
      <Footer />
    </div>
  );
}
