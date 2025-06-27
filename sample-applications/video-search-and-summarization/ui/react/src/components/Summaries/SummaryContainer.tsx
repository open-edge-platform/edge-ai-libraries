import { FC } from 'react';
import SummarySidebar from './SummarySideBar';
import Summary from './Summary';

export const SummaryMainContainer: FC = () => {
  return (
    <>
      <SummarySidebar />
      <Summary />
    </>
  );
};

export default SummaryMainContainer;
