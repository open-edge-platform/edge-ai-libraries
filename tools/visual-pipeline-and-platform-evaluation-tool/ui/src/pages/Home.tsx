import { useGetPipelinesQuery } from "@/api/api.generated.ts";

const Home = () => {
  const { data: pipelines, isSuccess } = useGetPipelinesQuery();

  if (isSuccess && pipelines) {
    return (
      <div>
        <ul>
          {pipelines.map((pipeline) => {
            const id = `${pipeline.name}-${pipeline.version}`;
            return (
              <li key={id}>
                <h1>{pipeline.version}</h1>
                <p>{pipeline.description}</p>
                <hr />
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return <div>Home</div>;
};

export default Home;
