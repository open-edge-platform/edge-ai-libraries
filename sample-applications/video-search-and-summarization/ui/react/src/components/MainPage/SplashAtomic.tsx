import { FC } from 'react';
import SearchMainContainer from '../Search/SearchContainer';
import SummaryMainContainer from '../Summaries/SummaryContainer';

export const SplashAtomic: FC = () => {
  return (
    <>
      <h3>SOMETING</h3>
    </>
  );
};

export const SplashAtomicSearch: FC = () => {
  return <SearchMainContainer />;
};

export const SplashAtomicSummary: FC = () => {
  return (
    <>
      <SummaryMainContainer />
    </>
  );
};
